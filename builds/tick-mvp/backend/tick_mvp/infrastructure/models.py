from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import BYTEA, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    active_trading_mode: Mapped[str] = mapped_column(Text, nullable=False, default="live")
    last_login_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TradingProfile(Base, TimestampMixin):
    __tablename__ = "trading_profiles"
    __table_args__ = (UniqueConstraint("user_id", "mode"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    current_season: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    starting_balance_usd: Mapped[object | None] = mapped_column(Numeric)
    balance_usd: Mapped[object | None] = mapped_column(Numeric)
    reset_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_reset_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))


class DemoProfileReset(Base):
    __tablename__ = "demo_profile_resets"
    __table_args__ = (UniqueConstraint("profile_id", "ended_season"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("trading_profiles.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    ended_season: Mapped[int] = mapped_column(Integer, nullable=False)
    starting_balance_usd: Mapped[object] = mapped_column(Numeric, nullable=False)
    ending_balance_usd: Mapped[object] = mapped_column(Numeric, nullable=False)
    realized_pnl_usd: Mapped[object] = mapped_column(Numeric, nullable=False)
    trade_count: Mapped[int] = mapped_column(Integer, nullable=False)
    win_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reset_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class AuthIdentity(Base, TimestampMixin):
    __tablename__ = "auth_identities"
    __table_args__ = (UniqueConstraint("provider", "provider_subject"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_subject: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    redeemed_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    redeemed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Asset(Base, TimestampMixin):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("chain_id", "address"),
        UniqueConstraint("symbol", "chain_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    chain_id: Mapped[int] = mapped_column(Integer, nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    decimals: Mapped[int] = mapped_column(Integer, nullable=False)
    asset_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class WalletAccount(Base, TimestampMixin):
    __tablename__ = "wallet_accounts"
    __table_args__ = (UniqueConstraint("chain_id", "address"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    chain_id: Mapped[int] = mapped_column(Integer, nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    wallet_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    custody_provider: Mapped[str] = mapped_column(Text, nullable=False)
    custody_key_ref: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_private_key: Mapped[bytes | None] = mapped_column(BYTEA)
    gas_wallet: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    trading_mode: Mapped[str] = mapped_column(Text, nullable=False, default="live")
    profile_season: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    venue: Mapped[str] = mapped_column(Text, nullable=False)
    market: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    ticket_usd: Mapped[object] = mapped_column(Numeric, nullable=False)
    leverage: Mapped[object] = mapped_column(Numeric, nullable=False)
    notional_usd: Mapped[object] = mapped_column(Numeric, nullable=False)
    max_loss_usd: Mapped[object | None] = mapped_column(Numeric)
    take_profit_usd: Mapped[object | None] = mapped_column(Numeric)
    estimated_open_cost_usd: Mapped[object] = mapped_column(Numeric, nullable=False, default=0)
    estimated_close_cost_usd: Mapped[object] = mapped_column(Numeric, nullable=False, default=0)
    estimated_round_trip_cost_usd: Mapped[object] = mapped_column(Numeric, nullable=False, default=0)
    liquidation_price: Mapped[object | None] = mapped_column(Numeric)
    stop_loss_price: Mapped[object | None] = mapped_column(Numeric)
    take_profit_price: Mapped[object | None] = mapped_column(Numeric)
    opening_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    risk_decision_id: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)


class TradeIntent(Base, TimestampMixin):
    __tablename__ = "trade_intents"
    __table_args__ = (UniqueConstraint("user_id", "trading_mode", "profile_season", "idempotency_key"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    trading_mode: Mapped[str] = mapped_column(Text, nullable=False, default="live")
    profile_season: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    quote_id: Mapped[str | None] = mapped_column(ForeignKey("quotes.id"))
    position_id: Mapped[str | None] = mapped_column(Text)
    wallet_id: Mapped[str | None] = mapped_column(ForeignKey("wallet_accounts.id"))
    market: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class ExecutionAttempt(Base, TimestampMixin):
    __tablename__ = "execution_attempts"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    trade_intent_id: Mapped[str] = mapped_column(ForeignKey("trade_intents.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    trading_mode: Mapped[str] = mapped_column(Text, nullable=False, default="live")
    profile_season: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    venue: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    nonce: Mapped[int | None] = mapped_column(BigInteger)
    tx_hash: Mapped[str | None] = mapped_column(Text)
    raw_tx_ref: Mapped[str | None] = mapped_column(Text)
    gas_payer_wallet_id: Mapped[str | None] = mapped_column(ForeignKey("wallet_accounts.id"))
    gas_cost_native: Mapped[object | None] = mapped_column(Numeric)
    gas_cost_usd: Mapped[object | None] = mapped_column(Numeric)
    gas_charge_asset: Mapped[str | None] = mapped_column(Text)
    gas_charge_amount: Mapped[object | None] = mapped_column(Numeric)
    error: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class Position(Base, TimestampMixin):
    __tablename__ = "positions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    trading_mode: Mapped[str] = mapped_column(Text, nullable=False, default="live")
    profile_season: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    wallet_id: Mapped[str | None] = mapped_column(ForeignKey("wallet_accounts.id"))
    venue: Mapped[str] = mapped_column(Text, nullable=False)
    venue_position_id: Mapped[str | None] = mapped_column(Text)
    market: Mapped[str] = mapped_column(Text, nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    quote_id: Mapped[str | None] = mapped_column(ForeignKey("quotes.id"))
    open_intent_id: Mapped[str | None] = mapped_column(ForeignKey("trade_intents.id"))
    close_intent_id: Mapped[str | None] = mapped_column(ForeignKey("trade_intents.id"))
    ticket_usd: Mapped[object] = mapped_column(Numeric, nullable=False)
    leverage: Mapped[object] = mapped_column(Numeric, nullable=False)
    notional_usd: Mapped[object] = mapped_column(Numeric, nullable=False)
    entry_price: Mapped[object | None] = mapped_column(Numeric)
    stop_loss_price: Mapped[object | None] = mapped_column(Numeric)
    take_profit_price: Mapped[object | None] = mapped_column(Numeric)
    liquidation_price: Mapped[object | None] = mapped_column(Numeric)
    opened_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class Withdrawal(Base, TimestampMixin):
    __tablename__ = "withdrawals"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    wallet_id: Mapped[str] = mapped_column(ForeignKey("wallet_accounts.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    asset: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[object] = mapped_column(Numeric, nullable=False)
    destination_address: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    nonce: Mapped[int | None] = mapped_column(BigInteger)
    tx_hash: Mapped[str | None] = mapped_column(Text)
    gas_cost_native: Mapped[object | None] = mapped_column(Numeric)
    gas_cost_usd: Mapped[object | None] = mapped_column(Numeric)
    gas_charge_asset: Mapped[str | None] = mapped_column(Text)
    gas_charge_amount: Mapped[object | None] = mapped_column(Numeric)
    error: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class GasTopup(Base, TimestampMixin):
    __tablename__ = "gas_topups"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    wallet_id: Mapped[str] = mapped_column(ForeignKey("wallet_accounts.id"), nullable=False)
    amount_native: Mapped[object] = mapped_column(Numeric, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    nonce: Mapped[int | None] = mapped_column(BigInteger)
    tx_hash: Mapped[str | None] = mapped_column(Text)
    gas_cost_native: Mapped[object | None] = mapped_column(Numeric)
    error: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class VenueEvent(Base):
    __tablename__ = "venue_events"
    __table_args__ = (UniqueConstraint("chain_id", "transaction_hash", "log_index"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    position_id: Mapped[str | None] = mapped_column(ForeignKey("positions.id"))
    execution_attempt_id: Mapped[str | None] = mapped_column(ForeignKey("execution_attempts.id"))
    venue: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    chain_id: Mapped[int | None] = mapped_column(Integer)
    block_number: Mapped[int | None] = mapped_column(BigInteger)
    block_hash: Mapped[str | None] = mapped_column(Text)
    transaction_hash: Mapped[str | None] = mapped_column(Text)
    log_index: Mapped[int | None] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    observed_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Reconciliation(Base, TimestampMixin):
    __tablename__ = "reconciliations"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    position_id: Mapped[str] = mapped_column(ForeignKey("positions.id"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    venue_realized_pnl_usd: Mapped[object | None] = mapped_column(Numeric)
    wallet_delta_usd: Mapped[object | None] = mapped_column(Numeric)
    difference_usd: Mapped[object | None] = mapped_column(Numeric)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class LedgerEvent(Base):
    __tablename__ = "ledger_events"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    trading_mode: Mapped[str] = mapped_column(Text, nullable=False, default="live")
    profile_season: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    position_id: Mapped[str | None] = mapped_column(ForeignKey("positions.id"))
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    asset: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[object] = mapped_column(Numeric, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    execution_attempt_id: Mapped[str | None] = mapped_column(ForeignKey("execution_attempts.id"))
    withdrawal_id: Mapped[str | None] = mapped_column(ForeignKey("withdrawals.id"))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
