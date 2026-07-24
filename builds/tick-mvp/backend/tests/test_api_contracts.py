from tick_mvp.app import create_app
from tick_mvp.auth import create_session_token, verify_session_token
from tick_mvp.schemas import CloseRequest, OpenRequest, QuoteRequest, WithdrawalRequest
from tick_mvp.states import PositionStatus
from tick_mvp.store import MemoryStore


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
        ),
    )
    assert quote.market == "BTCDEGEN-USD"
    assert quote.notionalUsd == 5000
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


def test_google_user_gets_platform_wallet_and_deposit_address() -> None:
    store = MemoryStore(default_venue="gtrade")

    user, wallet = store.upsert_google_user(
        provider_subject="google-subject-1",
        email="Alice@Example.com",
        display_name="Alice",
        avatar_url=None,
        chain_id=42161,
        custody_provider="encrypted_postgres",
    )

    assert user.email == "alice@example.com"
    assert wallet.userId == user.id
    assert wallet.chainId == 42161
    assert wallet.address.startswith("0x")

    deposit = store.deposit_address(user.id)
    assert deposit.address == wallet.address
    assert deposit.asset == "USDC"


def test_withdrawal_request_is_idempotent() -> None:
    store = MemoryStore(default_venue="gtrade")
    user, _ = store.upsert_google_user(
        provider_subject="google-subject-2",
        email="bob@example.com",
        display_name="Bob",
        avatar_url=None,
        chain_id=42161,
        custody_provider="encrypted_postgres",
    )

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


def test_session_token_round_trip() -> None:
    token = create_session_token(user_id="alice", wallet_address="0xabc", secret="secret", ttl_seconds=60)
    session = verify_session_token(token, secret="secret")
    assert session.user_id == "alice"
    assert session.wallet_address == "0xabc"


def test_api_routes_are_present() -> None:
    app = create_app(MemoryStore(default_venue="gtrade"))
    paths = {route.path for route in app.routes}
    assert "/api/auth/dev-session" in paths
    assert "/api/auth/google" in paths
    assert "/api/me" in paths
    assert "/api/wallet/deposit-address" in paths
    assert "/api/wallet/withdrawals" in paths
    assert "/api/trade/quote" in paths
    assert "/api/trade/open" in paths
    assert "/api/trade/close" in paths
    assert "/api/state" in paths
