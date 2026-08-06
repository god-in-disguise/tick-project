from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Callable

from tick_mvp.core.config import Settings
from tick_mvp.domain.states import TradeSide
from tick_mvp.venues.avantis.catalog import market_pair
from tick_mvp.venues.avantis.market_data import AvantisMarketData
from tick_mvp.venues.avantis.pricing import normalize_open_quote
from tick_mvp.venues.avantis.runtime import AvantisError, AvantisRuntime
from tick_mvp.venues.base import (
    TransactionPreparedHandler,
    VenueCloseResult,
    VenueOpenResult,
    VenueQuote,
)


PRICE_SCALE = Decimal(10**10)
USDC_SCALE = Decimal(10**6)


class AvantisVenue:
    name = "avantis"

    def __init__(
        self,
        settings: Settings,
        runtime: AvantisRuntime | None = None,
        *,
        market_history: Any | None = None,
    ) -> None:
        self._settings = settings
        self._runtime = runtime or AvantisRuntime(settings)
        self._market_data = AvantisMarketData(
            self._runtime,
            market_history=market_history,
            poll_seconds=settings.avantis_price_poll_seconds,
        )

    def start(self) -> None:
        self._runtime.start()
        self._market_data.start()

    def start_market_data(self) -> None:
        self.start()

    def stop(self) -> None:
        self._market_data.stop()
        self._runtime.stop()

    def stop_market_data(self) -> None:
        self.stop()

    def health(self) -> dict[str, Any]:
        return {**self._runtime.health(), "marketData": self._market_data.health()}

    def supports_market(self, market: str) -> bool:
        return self._market_data.supports_market(market)

    def quote_open(
        self,
        *,
        market: str,
        side: TradeSide,
        ticket_usd: Decimal,
        leverage: Decimal,
        max_loss_usd: Decimal | None,
        take_profit_usd: Decimal | None,
    ) -> VenueQuote:
        pair = market_pair(self._runtime.catalog(), market)
        return normalize_open_quote(
            pair,
            price=self._runtime.price(pair),
            side=side,
            ticket_usd=ticket_usd,
            leverage=leverage,
            max_loss_usd=max_loss_usd,
            take_profit_usd=take_profit_usd,
            execution_enabled=self._settings.avantis_real_execution_enabled,
        )

    def open_position(
        self,
        *,
        private_key_hex: str,
        market: str,
        side: TradeSide,
        ticket_usd: Decimal,
        leverage: Decimal,
        quote_payload: dict[str, Any],
        stop_loss_price: Decimal | None,
        take_profit_price: Decimal | None,
        on_transaction_prepared: TransactionPreparedHandler | None = None,
    ) -> VenueOpenResult:
        del quote_payload
        if not self._settings.avantis_real_execution_enabled:
            raise AvantisError("Avantis live execution is disabled")
        result = self._runtime.open_position(
            private_key_hex=private_key_hex,
            market=market,
            side=side,
            ticket_usd=ticket_usd,
            leverage=leverage,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            on_transaction_prepared=on_transaction_prepared,
        )
        args = result.callback.get("args") or {}
        trade = args.get("t") or {}
        entry_price = _scaled(args.get("price") or trade.get("openPrice"), PRICE_SCALE)
        trade_index = int(trade["index"])
        pair_index = int(trade["pairIndex"])
        return VenueOpenResult(
            status="open",
            tx=result.tx,
            venue_position_id=f"{pair_index}:{trade_index}",
            entry_price=entry_price,
            liquidation_price=_liquidation_price(entry_price, side, leverage),
            stop_loss_price=_scaled_or_none(trade.get("sl"), PRICE_SCALE),
            take_profit_price=_scaled_or_none(trade.get("tp"), PRICE_SCALE),
            opened_at=_timestamp_or_now(trade.get("timestamp")),
            account_balance_before_usd=result.account_balance_before_usd,
            payload={
                "position": trade,
                "callback": result.callback,
                "detectionSource": result.callback.get("source"),
                "callbackTxHash": result.callback.get("transactionHash"),
            },
        )

    def close_position(
        self,
        *,
        private_key_hex: str,
        market: str,
        side: TradeSide,
        venue_position_id: str | None,
        on_transaction_prepared: TransactionPreparedHandler | None = None,
    ) -> VenueCloseResult:
        del side
        if not self._settings.avantis_real_execution_enabled:
            raise AvantisError("Avantis live execution is disabled")
        result = self._runtime.close_position(
            private_key_hex=private_key_hex,
            market=market,
            venue_position_id=venue_position_id,
            on_transaction_prepared=on_transaction_prepared,
        )
        args = result.callback.get("args") or {}
        trade = args.get("t") or {}
        returned = _scaled(args.get("usdcSentToTrader"), USDC_SCALE) or Decimal(0)
        collateral = _scaled(trade.get("initialPosToken"), USDC_SCALE) or Decimal(0)
        return VenueCloseResult(
            status="closed",
            tx=result.tx,
            closed_at=datetime.now(UTC),
            venue_realized_pnl_usd=returned - collateral,
            account_balance_after_usd=None,
            close_cashflow_usd=returned,
            payload={
                "callback": result.callback,
                "exitPrice": str(_scaled(args.get("price"), PRICE_SCALE) or ""),
                "returnedCollateralUsd": str(returned),
                "detectionSource": result.callback.get("source"),
                "callbackTxHash": result.callback.get("transactionHash"),
            },
        )

    def prepare_wallet(
        self,
        *,
        private_key_hex: str,
        required_collateral_usd: Decimal,
        ensure_transaction_gas: Callable[..., Any] | None = None,
    ) -> dict[str, Any]:
        del ensure_transaction_gas
        return self._runtime.prepare_wallet(private_key_hex, required_collateral_usd)

    def collateral_balance_usd(self, *, private_key_hex: str) -> Decimal:
        return self._runtime.balance(private_key_hex)

    def recover_execution(
        self,
        *,
        private_key_hex: str,
        market: str,
        venue_position_id: str | None,
        tx_hash: str,
        signed_raw_transaction: str | None,
    ) -> dict[str, Any]:
        return self._runtime.recover(
            private_key_hex=private_key_hex,
            market=market,
            venue_position_id=venue_position_id,
            tx_hash=tx_hash,
            signed_raw_transaction=signed_raw_transaction,
        )

    def markets(self, *, limit: int = 10) -> dict[str, Any]:
        return self._market_data.markets(
            execution_enabled=self._settings.avantis_real_execution_enabled,
            limit=limit,
        )

    def chart(self, market: str, *, window_seconds: int = 90) -> dict[str, Any]:
        return self._market_data.chart(market, window_seconds=window_seconds)

    def tape(self, market: str, *, since: int) -> dict[str, Any]:
        return self._market_data.tape(market, since=since)


def _scaled(value: Any, scale: Decimal) -> Decimal | None:
    return Decimal(str(value)) / scale if value is not None else None


def _scaled_or_none(value: Any, scale: Decimal) -> Decimal | None:
    if value in (None, 0, "0"):
        return None
    return _scaled(value, scale)


def _liquidation_price(
    entry_price: Decimal | None,
    side: TradeSide,
    leverage: Decimal,
) -> Decimal | None:
    if entry_price is None or leverage <= 0:
        return None
    move = Decimal("0.8") / leverage
    return entry_price * (
        Decimal(1) - move if side == TradeSide.LONG else Decimal(1) + move
    )


def _timestamp_or_now(value: Any) -> datetime:
    if value is None:
        return datetime.now(UTC)
    return datetime.fromtimestamp(int(value), UTC)
