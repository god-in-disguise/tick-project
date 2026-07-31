import pytest
from fastapi import HTTPException

from tick_mvp.app import create_app
from tick_mvp.api.app import (
    _check_invite_rate_limit,
    _market_snapshot,
    _record_invite_failure,
    _session,
)
from tick_mvp.auth import create_session_token, verify_session_token
from tick_mvp.core.config import get_settings
from tick_mvp.domain.invitations import InviteAuthError, hash_invite_code
from tick_mvp.schemas import CloseRequest, OpenRequest, QuoteRequest, WithdrawalRequest
from tick_mvp.states import AuthProvider, PositionStatus, UserStatus
from tick_mvp.store import MemoryStore
from tick_mvp.venues.router import VenueRouter


def test_quote_open_close_contract() -> None:
    store = MemoryStore(default_venue="gtrade")

    quote = store.create_quote(
        "dev-user",
        QuoteRequest(
            market="BTCDEGEN/USD",
            side="long",
            ticketUsd="50",
            leverage="100",
            maxLossUsd="10",
            takeProfitUsd="20",
        ),
    )
    assert quote.market == "BTCDEGEN-USD"
    assert quote.notionalUsd == 5000
    assert quote.takeProfitUsd == 20
    assert quote.openingAllowed is True

    opened = store.accept_open("dev-user", OpenRequest(quoteId=quote.quoteId, idempotencyKey="open-key-0001"))
    assert opened.intent.action == "open"
    assert opened.executionAttempt.status == "created"
    assert opened.position is not None
    assert opened.position.status == PositionStatus.OPENING

    repeated = store.accept_open("dev-user", OpenRequest(quoteId=quote.quoteId, idempotencyKey="open-key-0001"))
    assert repeated.executionAttempt.id == opened.executionAttempt.id

    closed = store.accept_close("dev-user", CloseRequest(positionId=opened.position.id, idempotencyKey="close-key-0001"))
    assert closed.intent.action == "close"
    assert closed.position is not None
    assert closed.position.status == PositionStatus.CLOSING

    state = store.state("dev-user")
    assert len(state.positions) == 1
    assert len(state.executionAttempts) == 2
    assert len(state.reconciliations) == 1


def test_idempotency_key_is_bound_to_payload() -> None:
    store = MemoryStore(default_venue="gtrade")
    first = store.create_quote("dev-user", QuoteRequest(market="ETHDEGEN/USD", side="long", ticketUsd="10", leverage="100"))
    second = store.create_quote("dev-user", QuoteRequest(market="SOLDEGEN/USD", side="long", ticketUsd="10", leverage="100"))

    store.accept_open("dev-user", OpenRequest(quoteId=first.quoteId, idempotencyKey="same-key-0001"))
    try:
        store.accept_open("dev-user", OpenRequest(quoteId=second.quoteId, idempotencyKey="same-key-0001"))
    except Exception as exc:
        assert "idempotency key reused" in str(exc)
    else:
        raise AssertionError("expected idempotency conflict")


def test_one_active_position_per_user() -> None:
    store = MemoryStore(default_venue="gtrade")
    first = store.create_quote("dev-user", QuoteRequest(market="BTCDEGEN/USD", side="long", ticketUsd="10", leverage="100"))
    second = store.create_quote("dev-user", QuoteRequest(market="ETHDEGEN/USD", side="short", ticketUsd="10", leverage="100"))

    store.accept_open("dev-user", OpenRequest(quoteId=first.quoteId, idempotencyKey="open-one-0001"))

    try:
        store.accept_open("dev-user", OpenRequest(quoteId=second.quoteId, idempotencyKey="open-two-0001"))
    except Exception as exc:
        assert "active position" in str(exc)
    else:
        raise AssertionError("expected active-position conflict")


def test_invite_user_gets_platform_wallet_and_deposit_address() -> None:
    store = MemoryStore(default_venue="gtrade")

    user, wallet = store.upsert_auth_user(
        provider=AuthProvider.INVITE_CODE,
        provider_subject="invite-subject-1",
        email="invite+subject-1@pending.tick.local",
        display_name="Alice",
        avatar_url=None,
        chain_id=42161,
        custody_provider="encrypted_postgres",
    )

    assert user.email.endswith("@pending.tick.local")
    assert wallet.userId == user.id
    assert wallet.chainId == 42161
    assert wallet.address.startswith("0x")

    deposit = store.deposit_address(user.id)
    assert deposit.address == wallet.address
    assert deposit.asset == "USDC"


def test_invite_code_creates_and_reuses_one_wallet() -> None:
    store = MemoryStore(default_venue="gtrade")
    settings = get_settings()
    raw_code = "tick_private_alice"
    code_hash = hash_invite_code(raw_code, secret=settings.tick_invite_code_secret)
    store.create_invite_code(
        code_hash=code_hash,
        display_name="Chronos",
    )

    first_user, first_wallet = store.redeem_invite_code(
        code_hash=code_hash,
        chain_id=42161,
        custody_provider="encrypted_postgres",
    )
    second_user, second_wallet = store.redeem_invite_code(
        code_hash=code_hash,
        chain_id=42161,
        custody_provider="encrypted_postgres",
    )

    assert first_user.authProvider == "invite_code"
    assert first_user.displayName == "Chronos"
    assert second_user.id == first_user.id
    assert first_user.email.endswith("@pending.tick.local")
    assert second_wallet.id == first_wallet.id
    assert second_wallet.address == first_wallet.address


def test_unknown_invite_code_is_rejected() -> None:
    store = MemoryStore(default_venue="gtrade")
    settings = get_settings()
    code_hash = hash_invite_code("tick_private_alice", secret=settings.tick_invite_code_secret)
    store.create_invite_code(code_hash=code_hash)

    try:
        store.redeem_invite_code(
            code_hash=hash_invite_code("wrong-code", secret=settings.tick_invite_code_secret),
            chain_id=42161,
            custody_provider="encrypted_postgres",
        )
    except InviteAuthError as exc:
        assert str(exc) == "invalid or expired invite"
    else:
        raise AssertionError("expected unknown invite rejection")


def test_withdrawal_request_is_idempotent() -> None:
    store = MemoryStore(default_venue="gtrade")
    user, _ = _test_user(store, "withdrawal", "Bob")

    request = WithdrawalRequest(
        amount="12.50",
        destinationAddress="0x1111111111111111111111111111111111111111",
        idempotencyKey="withdraw-key-0001",
    )
    first = store.request_withdrawal(user.id, request)
    second = store.request_withdrawal(user.id, request)

    assert second.id == first.id
    assert first.status == "requested"
    assert store.state(user.id).withdrawals[0].id == first.id


def test_pending_withdrawal_blocks_a_new_position() -> None:
    store = MemoryStore(default_venue="gtrade")
    user, _ = _test_user(store, "withdrawal-lock", "Withdrawal Lock")
    store.request_withdrawal(
        user.id,
        WithdrawalRequest(
            amount="1",
            destinationAddress="0x1111111111111111111111111111111111111111",
            idempotencyKey="withdraw-lock-0001",
        ),
    )
    quote = store.create_quote(
        user.id,
        QuoteRequest(
            market="BTCDEGEN/USD",
            side="long",
            ticketUsd="10",
            leverage="100",
        ),
    )

    try:
        store.accept_open(
            user.id,
            OpenRequest(quoteId=quote.quoteId, idempotencyKey="open-lock-0001"),
        )
    except Exception as exc:
        assert "pending withdrawal" in str(exc)
    else:
        raise AssertionError("expected pending-withdrawal conflict")


def test_active_position_blocks_withdrawal() -> None:
    store = MemoryStore(default_venue="gtrade")
    user, _ = _test_user(store, "position-lock", "Position Lock")
    quote = store.create_quote(
        user.id,
        QuoteRequest(
            market="BTCDEGEN/USD",
            side="long",
            ticketUsd="10",
            leverage="100",
        ),
    )
    store.accept_open(
        user.id,
        OpenRequest(quoteId=quote.quoteId, idempotencyKey="open-position-lock"),
    )

    try:
        store.request_withdrawal(
            user.id,
            WithdrawalRequest(
                amount="1",
                destinationAddress="0x1111111111111111111111111111111111111111",
                idempotencyKey="withdraw-position-lock",
            ),
        )
    except Exception as exc:
        assert "position is active" in str(exc)
    else:
        raise AssertionError("expected active-position conflict")


def test_session_token_round_trip() -> None:
    token = create_session_token(user_id="alice", wallet_address="0xabc", secret="secret", ttl_seconds=60)
    session = verify_session_token(token, secret="secret")
    assert session.user_id == "alice"
    assert session.wallet_address == "0xabc"


def test_production_rejects_missing_session(monkeypatch) -> None:
    monkeypatch.setenv("TICK_ENV", "production")
    get_settings.cache_clear()
    try:
        with pytest.raises(HTTPException) as exc_info:
            _session(create_app(), None, None)
        assert exc_info.value.status_code == 401
    finally:
        get_settings.cache_clear()


def test_production_rejects_disabled_user_with_valid_token(monkeypatch) -> None:
    monkeypatch.setenv("TICK_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "disabled-user-test-secret")
    get_settings.cache_clear()
    try:
        store = MemoryStore(default_venue="gtrade")
        user, wallet = _test_user(store, "disabled", "Disabled User")
        store._users[user.id] = user.model_copy(update={"status": UserStatus.DISABLED})
        app = create_app(store)
        token = create_session_token(
            user_id=user.id,
            wallet_address=wallet.address,
            secret="disabled-user-test-secret",
            ttl_seconds=60,
        )

        with pytest.raises(HTTPException) as exc_info:
            _session(app, f"Bearer {token}", None)

        assert exc_info.value.status_code == 403
    finally:
        get_settings.cache_clear()


def test_invite_login_rate_limits_repeated_failures(monkeypatch) -> None:
    monkeypatch.setenv("TICK_ENV", "production")
    get_settings.cache_clear()
    try:
        app = create_app(MemoryStore(default_venue="gtrade"))
        for _ in range(10):
            _check_invite_rate_limit(app, "test-client")
            _record_invite_failure(app, "test-client")

        with pytest.raises(HTTPException) as exc_info:
            _check_invite_rate_limit(app, "test-client")
        assert exc_info.value.status_code == 429
    finally:
        get_settings.cache_clear()


def test_api_routes_are_present() -> None:
    app = create_app(MemoryStore(default_venue="gtrade"))
    paths = {route.path for route in app.routes}
    assert "/api/auth/invite" in paths
    assert "/api/me" in paths
    assert "/api/wallet/deposit-address" in paths
    assert "/api/wallet/balances" in paths
    assert "/api/wallet/withdrawals" in paths
    assert "/api/trade/quote" in paths
    assert "/api/trade/open" in paths
    assert "/api/trade/close" in paths
    assert "/api/state" in paths
    assert "/api/events" in paths
    assert "/api/tapes" in paths


def test_venue_router_forwards_default_feed_health() -> None:
    class HealthyVenue:
        def health(self):
            return {"prices": {"running": True, "marketCount": 13}}

    router = VenueRouter({"gtrade": HealthyVenue()}, default_venue="gtrade")

    health = router.health()

    assert health is not None
    assert health["prices"]["marketCount"] == 13
    assert health["venues"]["gtrade"]["prices"]["running"] is True


def test_markets_can_include_retained_tape() -> None:
    class MarketStore:
        def markets(self, *, limit: int = 10):
            return {
                "venue": "test",
                "markets": [
                    {
                        "market": "TEST-USD",
                        "symbol": "TEST",
                        "price": 10,
                    }
                ][:limit],
            }

        def chart(self, market: str, *, window_seconds: int = 90):
            assert market == "TEST-USD"
            assert window_seconds == 90
            return {
                "lastSeq": 7,
                "observations": [
                    {"seq": 7, "receivedTs": 1000, "price": 10, "unchanged": False}
                ],
            }

    payload = _market_snapshot(
        MarketStore(),
        limit=10,
        include_tape=True,
        window_seconds=90,
    )
    market = payload["markets"][0]
    assert market["sequence"] == 7
    assert market["observations"][0]["price"] == 10


def _test_user(store: MemoryStore, subject: str, name: str):
    return store.upsert_auth_user(
        provider=AuthProvider.INVITE_CODE,
        provider_subject=f"invite-{subject}",
        email=f"invite+{subject}@pending.tick.local",
        display_name=name,
        avatar_url=None,
        chain_id=42161,
        custody_provider="encrypted_postgres",
    )
