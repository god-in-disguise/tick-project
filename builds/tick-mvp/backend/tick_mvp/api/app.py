from fastapi import FastAPI, Header, HTTPException, status

from tick_mvp.api.auth import AuthError, UserSession, create_session_token, verify_session_token
from tick_mvp.core.config import get_settings
from tick_mvp.domain.schemas import (
    AcceptedTradeResponse,
    CloseRequest,
    DevSessionRequest,
    OpenRequest,
    QuoteRequest,
    QuoteResponse,
    SessionResponse,
    StateResponse,
)
from tick_mvp.infrastructure.memory_store import MemoryStore, StoreConflict, StoreNotFound
from tick_mvp.infrastructure.queue import enqueue_execution_attempt


def create_app(store: MemoryStore | None = None) -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="TICK MVP API")
    app.state.store = store or MemoryStore(default_venue=settings.default_venue, quote_ttl_seconds=settings.quote_ttl_seconds)

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

    @app.post("/api/auth/dev-session", response_model=SessionResponse)
    def dev_session(body: DevSessionRequest) -> SessionResponse:
        current_settings = get_settings()
        if not current_settings.tick_allow_dev_auth:
            raise HTTPException(status_code=404, detail="dev auth is disabled")
        token = create_session_token(
            user_id=body.userId,
            wallet_address=body.walletAddress,
            secret=current_settings.jwt_secret,
            ttl_seconds=current_settings.jwt_ttl_seconds,
        )
        return SessionResponse(
            token=token,
            userId=body.userId,
            walletAddress=body.walletAddress,
            expiresIn=current_settings.jwt_ttl_seconds,
        )

    @app.get("/api/state", response_model=StateResponse)
    def state(authorization: str | None = Header(default=None), x_tick_user: str | None = Header(default=None)) -> StateResponse:
        return _store(app).state(_session(authorization, x_tick_user).user_id)

    @app.get("/api/positions")
    def positions(authorization: str | None = Header(default=None), x_tick_user: str | None = Header(default=None)) -> dict[str, object]:
        return {"positions": _store(app).state(_session(authorization, x_tick_user).user_id).positions}

    @app.post("/api/trade/quote", response_model=QuoteResponse)
    def quote(body: QuoteRequest, authorization: str | None = Header(default=None), x_tick_user: str | None = Header(default=None)) -> QuoteResponse:
        return _store(app).create_quote(_session(authorization, x_tick_user).user_id, body)

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


def _store(app: FastAPI) -> MemoryStore:
    return app.state.store


async def _with_dispatch(accepted: AcceptedTradeResponse) -> AcceptedTradeResponse:
    if not get_settings().tick_enqueue_jobs:
        return accepted
    dispatch = await enqueue_execution_attempt(accepted.executionAttempt)
    return accepted.model_copy(update={"job": dispatch})


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
