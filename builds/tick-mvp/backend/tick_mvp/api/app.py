import asyncio
import hashlib
from contextlib import asynccontextmanager
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from tick_mvp.api.auth import AuthError, UserSession, create_session_token, verify_session_token
from tick_mvp.core.config import get_settings
from tick_mvp.domain.invitations import InviteAuthError, hash_invite_code
from tick_mvp.domain.schemas import (
    AcceptedTradeResponse,
    CloseRequest,
    DemoResetResponse,
    DepositAddressResponse,
    InviteSessionRequest,
    MeResponse,
    OpenRequest,
    QuoteRequest,
    QuoteResponse,
    SessionResponse,
    StateResponse,
    TradingModeRequest,
    TradingProfileResponse,
    WalletBalancesResponse,
    WithdrawalRequest,
    WithdrawalResponse,
)
from tick_mvp.infrastructure.memory_store import MemoryStore, StoreConflict, StoreNotFound
from tick_mvp.infrastructure.queue import (
    enqueue_execution_attempt,
    enqueue_wallet_preparation,
    enqueue_withdrawal_request,
)
from tick_mvp.venues.base import VenueError


@asynccontextmanager
async def _lifespan(app: FastAPI):
    current_settings = get_settings()
    if current_settings.tick_store_backend == "postgres" and current_settings.tick_run_migrations_on_start:
        from tick_mvp.infrastructure.database import run_sql_migrations

        run_sql_migrations(current_settings.database_url)
    store = getattr(app.state, "store", None)
    start = getattr(store, "start", None)
    if start is not None:
        start()
    try:
        yield
    finally:
        stop = getattr(store, "stop", None)
        if stop is not None:
            stop()


def create_app(store: Any | None = None) -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="TICK MVP API", lifespan=_lifespan)
    origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )
    app.state.store = store or _default_store()

    @app.get("/health")
    def health() -> dict[str, object]:
        current_settings = get_settings()
        return {
            "ok": True,
            "env": current_settings.tick_env,
            "venue": current_settings.default_venue,
            "chainId": current_settings.arb_chain_id,
        }

    @app.get("/ready")
    def ready() -> dict[str, object]:
        return {"ok": True}

    @app.post("/api/auth/invite", response_model=SessionResponse)
    def invite_session(body: InviteSessionRequest) -> SessionResponse:
        current_settings = get_settings()
        try:
            user, wallet = _store(app).redeem_invite_code(
                code_hash=hash_invite_code(
                    body.accessCode,
                    secret=current_settings.tick_invite_code_secret,
                ),
                chain_id=current_settings.arb_chain_id,
                custody_provider=current_settings.custody_provider,
            )
        except InviteAuthError as exc:
            raise HTTPException(status_code=401, detail="invalid or expired invite") from exc
        token = create_session_token(
            user_id=user.id,
            wallet_address=wallet.address,
            secret=current_settings.jwt_secret,
            ttl_seconds=current_settings.jwt_ttl_seconds,
        )
        return SessionResponse(
            token=token,
            userId=user.id,
            walletAddress=wallet.address,
            expiresIn=current_settings.jwt_ttl_seconds,
            user=user,
            wallet=wallet,
        )

    @app.get("/api/me", response_model=MeResponse)
    def me(authorization: str | None = Header(default=None), x_tick_user: str | None = Header(default=None)) -> MeResponse:
        session = _session(authorization, x_tick_user)
        try:
            store = _store(app)
            return MeResponse(
                user=store.user(session.user_id),
                wallet=store.wallet_for_user(session.user_id),
                tradingProfile=store.trading_profile(session.user_id),
            )
        except StoreNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/trading-profile/mode", response_model=TradingProfileResponse)
    def switch_trading_mode(
        body: TradingModeRequest,
        authorization: str | None = Header(default=None),
        x_tick_user: str | None = Header(default=None),
    ) -> TradingProfileResponse:
        try:
            return _store(app).switch_trading_mode(
                _session(authorization, x_tick_user).user_id,
                body.mode,
            )
        except StoreNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except StoreConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/trading-profile/demo/reset", response_model=DemoResetResponse)
    def reset_demo_profile(
        authorization: str | None = Header(default=None),
        x_tick_user: str | None = Header(default=None),
    ) -> DemoResetResponse:
        try:
            return _store(app).reset_demo_profile(
                _session(authorization, x_tick_user).user_id,
            )
        except StoreNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except StoreConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/state", response_model=StateResponse)
    def state(authorization: str | None = Header(default=None), x_tick_user: str | None = Header(default=None)) -> StateResponse:
        return _store(app).state(_session(authorization, x_tick_user).user_id)

    @app.get("/api/events")
    async def events(
        request: Request,
        authorization: str | None = Header(default=None),
        x_tick_user: str | None = Header(default=None),
    ) -> StreamingResponse:
        user_id = _session(authorization, x_tick_user).user_id

        async def stream():
            last_version = ""
            idle_cycles = 0
            while not await request.is_disconnected():
                current = await asyncio.to_thread(_store(app).state, user_id)
                version = _state_version(current)
                if version != last_version:
                    last_version = version
                    idle_cycles = 0
                    yield f"event: state\ndata: {version}\n\n"
                else:
                    idle_cycles += 1
                    if idle_cycles >= 60:
                        idle_cycles = 0
                        yield ": keepalive\n\n"
                active = any(
                    position.status.value in {"opening", "open", "closing", "unknown"}
                    for position in current.positions
                )
                await asyncio.sleep(0.20 if active else 1.0)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/positions")
    def positions(authorization: str | None = Header(default=None), x_tick_user: str | None = Header(default=None)) -> dict[str, object]:
        return {"positions": _store(app).state(_session(authorization, x_tick_user).user_id).positions}

    @app.get("/api/markets")
    def markets(
        limit: int = Query(default=10, ge=1, le=20),
        include_tape: bool = Query(default=False, alias="includeTape"),
        window_seconds: int = Query(default=90, alias="windowSeconds", ge=30, le=300),
    ) -> dict[str, Any]:
        try:
            return _market_snapshot(
                _store(app),
                limit=limit,
                include_tape=include_tape,
                window_seconds=window_seconds,
            )
        except StoreNotFound as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/chart")
    def chart(
        market: str,
        window_seconds: int = Query(default=90, alias="windowSeconds", ge=30, le=3600),
    ) -> dict[str, Any]:
        try:
            return _store(app).chart(market, window_seconds=window_seconds)
        except StoreNotFound as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/tape")
    def tape(market: str, since: int = Query(default=0, ge=0)) -> dict[str, Any]:
        try:
            return _store(app).tape(market, since=since)
        except StoreNotFound as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/wallet/deposit-address", response_model=DepositAddressResponse)
    def deposit_address(authorization: str | None = Header(default=None), x_tick_user: str | None = Header(default=None)) -> DepositAddressResponse:
        try:
            store = _store(app)
            user_id = _session(authorization, x_tick_user).user_id
            if store.is_demo_mode(user_id):
                raise StoreConflict("deposits are unavailable in demo mode")
            return store.deposit_address(user_id)
        except StoreNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except StoreConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/wallet/balances", response_model=WalletBalancesResponse)
    def wallet_balances(authorization: str | None = Header(default=None), x_tick_user: str | None = Header(default=None)) -> WalletBalancesResponse:
        user_id = _session(authorization, x_tick_user).user_id
        try:
            store = _store(app)
            demo = store.demo_balances(user_id)
            if demo is not None:
                return demo
            wallet = store.wallet_for_user(user_id)
        except StoreNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        from tick_mvp.infrastructure.wallet_balances import read_wallet_balances

        return read_wallet_balances(
            wallet,
            get_settings(),
            gas_charges_usdc=store.reserved_gas_charges_usdc(user_id),
        )

    @app.post("/api/wallet/withdrawals", response_model=WithdrawalResponse, status_code=status.HTTP_202_ACCEPTED)
    async def request_withdrawal(
        body: WithdrawalRequest,
        authorization: str | None = Header(default=None),
        x_tick_user: str | None = Header(default=None),
    ) -> WithdrawalResponse:
        user_id = _session(authorization, x_tick_user).user_id
        try:
            store = _store(app)
            wallet = store.wallet_for_user(user_id)
            from tick_mvp.infrastructure.wallet_balances import read_wallet_balances

            balances = read_wallet_balances(
                wallet,
                get_settings(),
                gas_charges_usdc=store.reserved_gas_charges_usdc(user_id),
            )
            if balances.spendableUsdc is None:
                raise StoreConflict("wallet balance is temporarily unavailable")
            if body.amount > balances.spendableUsdc:
                raise StoreConflict(
                    f"insufficient spendable USDC: {balances.spendableUsdc:.6f} available"
                )
            withdrawal = store.request_withdrawal(user_id, body)
            if get_settings().tick_enqueue_jobs:
                await enqueue_withdrawal_request(withdrawal)
            return withdrawal
        except StoreNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except StoreConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/wallet/withdrawals")
    def withdrawals(authorization: str | None = Header(default=None), x_tick_user: str | None = Header(default=None)) -> dict[str, object]:
        return {"withdrawals": _store(app).state(_session(authorization, x_tick_user).user_id).withdrawals}

    @app.post("/api/trade/quote", response_model=QuoteResponse)
    def quote(
        body: QuoteRequest,
        background_tasks: BackgroundTasks,
        authorization: str | None = Header(default=None),
        x_tick_user: str | None = Header(default=None),
    ) -> QuoteResponse:
        user_id = _session(authorization, x_tick_user).user_id
        try:
            response = _store(app).create_quote(user_id, body)
        except VenueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if get_settings().tick_enqueue_jobs and response.tradingMode.value == "live":
            background_tasks.add_task(
                enqueue_wallet_preparation,
                user_id,
                str(response.ticketUsd),
            )
        return response

    @app.post("/api/trade/open", response_model=AcceptedTradeResponse, status_code=status.HTTP_202_ACCEPTED)
    async def open_trade(
        body: OpenRequest,
        authorization: str | None = Header(default=None),
        x_tick_user: str | None = Header(default=None),
    ) -> AcceptedTradeResponse:
        try:
            accepted = _store(app).accept_open(_session(authorization, x_tick_user).user_id, body)
            return await _with_dispatch(accepted)
        except StoreNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except StoreConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/trade/close", response_model=AcceptedTradeResponse, status_code=status.HTTP_202_ACCEPTED)
    async def close_trade(
        body: CloseRequest,
        authorization: str | None = Header(default=None),
        x_tick_user: str | None = Header(default=None),
    ) -> AcceptedTradeResponse:
        try:
            accepted = _store(app).accept_close(_session(authorization, x_tick_user).user_id, body)
            return await _with_dispatch(accepted)
        except StoreNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except StoreConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return app


def _store(app: FastAPI) -> Any:
    return app.state.store


def _default_store() -> Any:
    settings = get_settings()
    if settings.tick_store_backend == "postgres":
        from tick_mvp.infrastructure.sqlalchemy_store import SQLAlchemyStore
        from tick_mvp.venues.registry import create_quote_engine

        return SQLAlchemyStore(
            default_venue=settings.default_venue,
            quote_ttl_seconds=settings.quote_ttl_seconds,
            quote_engine=create_quote_engine(settings),
        )
    return MemoryStore(default_venue=settings.default_venue, quote_ttl_seconds=settings.quote_ttl_seconds)


async def _with_dispatch(accepted: AcceptedTradeResponse) -> AcceptedTradeResponse:
    if not get_settings().tick_enqueue_jobs:
        return accepted
    dispatch = await enqueue_execution_attempt(accepted.executionAttempt)
    return accepted.model_copy(update={"job": dispatch})


def _state_version(current: StateResponse) -> str:
    records = [
        *(f"p:{item.id}:{item.status}:{item.updatedAt.isoformat()}" for item in current.positions),
        *(f"e:{item.id}:{item.status}:{item.updatedAt.isoformat()}" for item in current.executionAttempts),
        *(f"r:{item.id}:{item.status}:{item.updatedAt.isoformat()}" for item in current.reconciliations),
        *(f"w:{item.id}:{item.status}:{item.updatedAt.isoformat()}" for item in current.withdrawals),
    ]
    if not records:
        return "empty"
    return hashlib.sha256("|".join(records).encode()).hexdigest()


def _market_snapshot(
    store: Any,
    *,
    limit: int,
    include_tape: bool,
    window_seconds: int,
) -> dict[str, Any]:
    payload = store.markets(limit=limit)
    if not include_tape:
        return payload

    enriched: list[dict[str, Any]] = []
    for market in payload.get("markets") or []:
        chart = store.chart(market["market"], window_seconds=window_seconds)
        enriched.append(
            {
                **market,
                "observations": chart.get("observations") or [],
                "sequence": int(chart.get("lastSeq") or 0),
            }
        )
    return {**payload, "markets": enriched}


def _session(authorization: str | None, dev_user_id: str | None) -> UserSession:
    settings = get_settings()
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="invalid authorization header")
        try:
            return verify_session_token(token, secret=settings.jwt_secret)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
    if settings.tick_allow_dev_auth:
        return UserSession(user_id=dev_user_id or "dev-user")
    raise HTTPException(status_code=401, detail="missing bearer token")

app = create_app()
