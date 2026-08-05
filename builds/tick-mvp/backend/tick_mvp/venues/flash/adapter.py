from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from tick_mvp.core.config import Settings
from tick_mvp.domain.states import TradeSide
from tick_mvp.venues.base import TransactionPreparedHandler, VenueCloseResult, VenueOpenResult, VenueQuote
from tick_mvp.venues.flash.client import FlashClient, FlashError
from tick_mvp.venues.flash.constants import MARKETS, market_config
from tick_mvp.venues.flash.funding import FlashSetupFunder
from tick_mvp.venues.flash.market_data import FlashMarketData
from tick_mvp.venues.flash.pricing import normalize_open_quote
from tick_mvp.venues.flash.wallet import FlashWalletExecutor


class FlashVenue:
    name = "flash"

    def __init__(
        self,
        settings: Settings,
        client: FlashClient | None = None,
        *,
        market_client: FlashClient | None = None,
        market_history: Any | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or FlashClient(settings.flash_api_url)
        self._market_client = market_client or FlashClient(settings.flash_api_url)
        self._market_data = FlashMarketData(
            self._market_client,
            market_history=market_history,
            poll_seconds=settings.flash_price_poll_seconds,
        )
        self._startup_health: dict[str, Any] | None = None
        self._startup_error: str | None = None
        self._setup_funder = FlashSetupFunder(
            settings.solana_rpc_url,
            settings.flash_setup_wallet_private_key,
            setup_target_sol=settings.flash_setup_target_sol,
        )
        self._wallet = FlashWalletExecutor(
            self._client,
            slippage_percentage=settings.flash_slippage_percentage,
            setup_funder=self._setup_funder,
        )

    def start(self) -> None:
        try:
            self._startup_health = self._client.health()
            self._startup_error = None
        except Exception as exc:
            self._startup_error = f"{type(exc).__name__}: {exc}"
        self._market_data.start()

    def start_market_data(self) -> None:
        self.start()

    def stop(self) -> None:
        self._market_data.stop()
        if self._market_client is not self._client:
            self._market_client.close()
        self._setup_funder.close()
        self._client.close()

    def stop_market_data(self) -> None:
        self.stop()

    def health(self) -> dict[str, Any]:
        try:
            live = self._client.health()
            error = None
        except Exception as exc:
            live = self._startup_health or {}
            error = f"{type(exc).__name__}: {exc}"
        return {
            "venue": self.name,
            **live,
            "marketData": self._market_data.health(),
            "setupFunding": {
                "configured": self._setup_funder.configured,
                "address": self._setup_funder.address,
                "targetSol": str(self._setup_funder.setup_target_sol),
            },
            "startupError": self._startup_error,
            "healthError": error,
        }

    def supports_market(self, market: str) -> bool:
        return market.strip().upper() in MARKETS

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
        config = market_config(market)
        response = self._client.quote_open(
            {
                "inputTokenSymbol": "USDC",
                "outputTokenSymbol": config.symbol,
                "inputAmountUi": str(ticket_usd),
                "leverage": float(leverage),
                "tradeType": side.value.upper(),
                "orderType": "MARKET",
                "slippagePercentage": str(self._settings.flash_slippage_percentage),
            }
        )
        return normalize_open_quote(
            config,
            response,
            side=side,
            ticket_usd=ticket_usd,
            requested_leverage=leverage,
            max_loss_usd=max_loss_usd,
            take_profit_usd=take_profit_usd,
            execution_enabled=self._settings.flash_real_execution_enabled,
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
        if not self._settings.flash_real_execution_enabled:
            raise FlashError("Flash live execution is disabled")
        return self._wallet.open_position(
            private_key=private_key_hex,
            market=market,
            side=side,
            ticket_usd=ticket_usd,
            leverage=leverage,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            on_transaction_prepared=on_transaction_prepared,
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
        if not self._settings.flash_real_execution_enabled:
            raise FlashError("Flash live execution is disabled")
        return self._wallet.close_position(
            private_key=private_key_hex,
            market=market,
            side=side,
            venue_position_id=venue_position_id,
            on_transaction_prepared=on_transaction_prepared,
        )

    def prepare_wallet(
        self,
        *,
        private_key_hex: str,
        required_collateral_usd: Decimal,
        ensure_transaction_gas: Callable[..., Any] | None = None,
    ) -> dict[str, Any]:
        del ensure_transaction_gas
        return self._wallet.prepare_wallet(private_key_hex, required_collateral_usd)

    def collateral_balance_usd(self, *, private_key_hex: str) -> Decimal:
        return self._wallet.collateral_balance_usd(private_key_hex)

    def recover_execution(
        self,
        *,
        private_key_hex: str,
        market: str,
        venue_position_id: str | None,
        tx_hash: str,
        signed_raw_transaction: str | None,
    ) -> dict[str, Any]:
        del market, signed_raw_transaction
        return self._wallet.recover_execution(
            private_key=private_key_hex,
            venue_position_id=venue_position_id,
            tx_hash=tx_hash,
        )

    def markets(self, *, limit: int = 10) -> dict[str, Any]:
        return self._market_data.markets(
            execution_enabled=self._settings.flash_real_execution_enabled,
            limit=limit,
        )

    def chart(self, market: str, *, window_seconds: int = 90) -> dict[str, Any]:
        market_config(market)
        return self._market_data.chart(market, window_seconds=window_seconds)

    def tape(self, market: str, *, since: int) -> dict[str, Any]:
        market_config(market)
        return self._market_data.tape(market, since=since)
