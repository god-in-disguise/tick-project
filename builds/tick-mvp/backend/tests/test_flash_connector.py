from dataclasses import replace
from decimal import Decimal

import pytest

from tick_mvp.core.config import Settings
from tick_mvp.domain.states import TradeSide
from tick_mvp.venues.flash.adapter import FlashVenue
from tick_mvp.venues.flash.client import FlashAmbiguousExecution, FlashClient, FlashError
from tick_mvp.venues.flash.constants import market_config
from tick_mvp.venues.flash.funding import SolanaWalletState
from tick_mvp.venues.flash.market_data import FlashMarketData
from tick_mvp.venues.flash.pricing import normalize_open_quote
from tick_mvp.venues.flash.signing import PreparedFlashTransaction
from tick_mvp.venues.flash.wallet import FlashWalletExecutor, _position_size_usd


XAU_QUOTE = {
    "newLeverage": "200.48",
    "newEntryPrice": "4048.6200",
    "newLiquidationPrice": "4032.4260",
    "entryFee": "0.37",
    "openPositionFeePercent": "0.02000",
    "availableLiquidity": "225945.20",
    "youPayUsdUi": "9.99",
    "youRecieveUsdUi": "1851.48",
    "maxPositionSizeUsd": "500000.00",
    "passesMaxPositionSize": True,
    "passesMaxExposure": True,
    "passesMaxUtilization": True,
}


def test_flash_xau_200x_quote_uses_effective_exposure_and_symmetric_cost() -> None:
    quote = normalize_open_quote(
        replace(
            market_config("FLASH-XAU-USD"),
            max_leverage=Decimal("200"),
        ),
        XAU_QUOTE,
        side=TradeSide.LONG,
        ticket_usd=Decimal("10"),
        requested_leverage=Decimal("200"),
        max_loss_usd=None,
        take_profit_usd=None,
        execution_enabled=True,
    )

    assert quote.notional_usd == Decimal("1851.48")
    assert quote.estimated_open_cost_usd == Decimal("0.37")
    assert quote.estimated_close_cost_usd == Decimal("0.370296")
    assert quote.estimated_round_trip_cost_usd == Decimal("0.740296")
    assert quote.liquidation_price == Decimal("4032.4260")
    assert quote.payload["requestedNotionalUsd"] == "2000"
    assert quote.payload["effectiveNotionalUsd"] == "1851.48"
    assert quote.opening_allowed is False
    assert quote.payload["openingBlockedReason"] == "market_not_canary_certified"


def test_flash_close_size_preserves_authoritative_six_decimals() -> None:
    position = {"position": {"sizeUsd": 4_165_894_110}}

    assert _position_size_usd(position) == Decimal("4165.894110")


class StateDrivenClient(FlashClient):
    def __init__(self, *, transition_after_submissions: int) -> None:
        super().__init__(
            "https://flash.invalid",
            hedge_seconds=0,
            poll_seconds=0,
        )
        self.transition_after_submissions = transition_after_submissions
        self.signed_payloads: list[str] = []

    def _submit_exact(self, prepared: PreparedFlashTransaction):
        self.signed_payloads.append(prepared.signed_transaction_base64)
        return {"signature": prepared.signature}

    def raw_basket(self, basket_pubkey: str):
        assert basket_pubkey == "basket"
        positions = (
            [{"position": {"sizeUsd": 10_000_000}}]
            if len(self.signed_payloads) >= self.transition_after_submissions
            else []
        )
        return {"account": {"positions": positions}, "source": "er"}


def test_flash_state_hedge_resends_identical_signed_transaction() -> None:
    client = StateDrivenClient(transition_after_submissions=2)
    prepared = PreparedFlashTransaction("sig", "signed-base64", {})

    result = client.submit_and_wait(
        prepared,
        basket_pubkey="basket",
        predicate=lambda snapshot: bool(snapshot["account"]["positions"]),
        timeout_seconds=0.1,
    )

    assert result["hedged"] is True
    assert client.signed_payloads == ["signed-base64", "signed-base64"]


def test_flash_ack_without_raw_transition_stays_ambiguous() -> None:
    client = StateDrivenClient(transition_after_submissions=1000)
    prepared = PreparedFlashTransaction("sig", "signed-base64", {})

    with pytest.raises(FlashAmbiguousExecution, match="acknowledged"):
        client.submit_and_wait(
            prepared,
            basket_pubkey="basket",
            predicate=lambda snapshot: bool(snapshot["account"]["positions"]),
            timeout_seconds=0.002,
        )


class QuoteClient:
    def quote_open(self, body):
        assert body["tradeType"] == "SHORT"
        assert body["outputTokenSymbol"] == "XAU"
        return {
            **XAU_QUOTE,
            "newLeverage": "100.24",
            "entryFee": "0.19",
            "youRecieveUsdUi": "925.74",
        }

    def close(self):
        return None


def test_flash_adapter_keeps_venue_terms_behind_normalized_quote() -> None:
    venue = FlashVenue(
        Settings(flash_real_execution_enabled=False),
        client=QuoteClient(),
    )

    quote = venue.quote_open(
        market="FLASH-XAU-USD",
        side=TradeSide.SHORT,
        ticket_usd=Decimal("10"),
        leverage=Decimal("100"),
        max_loss_usd=None,
        take_profit_usd=None,
    )

    assert quote.venue == "flash"
    assert quote.market == "FLASH-XAU-USD"
    assert quote.payload["symbol"] == "XAU"


def test_flash_synthetic_200x_is_not_an_initial_leverage() -> None:
    with pytest.raises(FlashError, match="at most 100x"):
        normalize_open_quote(
            market_config("FLASH-XAU-USD"),
            XAU_QUOTE,
            side=TradeSide.LONG,
            ticket_usd=Decimal("10"),
            requested_leverage=Decimal("200"),
            max_loss_usd=None,
            take_profit_usd=None,
            execution_enabled=True,
        )


class PriceClient:
    def __init__(self) -> None:
        self.timestamp = 1_000_000

    def prices(self):
        self.timestamp += 100_000
        return {
            "BTC": {
                "price": 6_345_000_000_000,
                "exponent": -8,
                "timestampUs": self.timestamp,
                "marketSession": "regular",
            }
        }


def test_flash_market_data_exposes_router_compatible_tape() -> None:
    feed = FlashMarketData(PriceClient(), poll_seconds=10)
    feed._refresh_once()
    payload = feed.chart("FLASH-BTC-USD", window_seconds=90)
    market = feed.markets(execution_enabled=False, limit=10)["markets"][0]

    assert payload["venue"] == "flash"
    assert payload["market"] == "FLASH-BTC-USD"
    assert payload["observations"][0]["price"] == "63450.00000000"
    assert payload["observations"][0]["seq"] == 1
    assert market["feeHurdlePct"] == Decimal("0.04")
    assert market["activitySurplusPct"] == Decimal("-0.04")
    assert market["minPositionSizeUsd"] == Decimal(0)
    assert market["minCollateralUsd"] == Decimal("10")
    assert market["minLeverage"] == Decimal("100")


class SetupClient:
    def __init__(self) -> None:
        self.basket = None
        self.available = Decimal(0)
        self.delegated = False
        self.paths: list[str] = []

    def owner(self, owner: str):
        return {"owner": owner, "basketPubkey": self.basket}

    def raw_basket(self, basket: str):
        assert basket == "basket"
        return {
            "source": "er" if self.delegated else "base",
            "account": {
                "debits": [
                    {
                        "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                        "amount": int(self.available * 1_000_000),
                    }
                ],
                "pendingCredits": [],
                "positions": [],
            },
        }

    def prepare(self, path, body, _keypair):
        self.paths.append(path)
        return PreparedFlashTransaction(
            signature=f"sig-{len(self.paths)}",
            signed_transaction_base64="signed",
            quote={"path": path, "body": body},
        )

    def submit_exact(self, prepared, *, skip_preflight):
        path = prepared.quote["path"]
        if path.endswith("init-basket"):
            self.basket = "basket"
        elif path.endswith("deposit-direct"):
            self.available += Decimal(prepared.quote["body"]["amount"])
        elif path.endswith("delegate-basket"):
            self.delegated = True
        return {"signature": prepared.signature, "skipPreflight": skip_preflight}


class SetupFunder:
    setup_target_sol = Decimal("0.075")

    def __init__(
        self,
        *,
        sol: Decimal = Decimal(0),
        usdc: Decimal = Decimal(0),
        deposited_usdc: Decimal = Decimal(0),
    ) -> None:
        self.sol = sol
        self.usdc = usdc
        self.deposited_usdc = deposited_usdc
        self.targets: list[Decimal] = []

    def wallet_state(self, _owner: str) -> SolanaWalletState:
        return SolanaWalletState(
            sol=self.sol,
            usdc=self.usdc,
            deposited_usdc=self.deposited_usdc,
        )

    def ensure_funded(self, owner: str, *, target_sol: Decimal):
        self.targets.append(target_sol)
        before = self.sol
        self.sol = max(self.sol, target_sol)
        return {
            "funded": self.sol > before,
            "wallet": owner,
            "solBefore": str(before),
            "solAfter": str(self.sol),
        }


def test_flash_wallet_first_preparation_initializes_and_funds_once(monkeypatch) -> None:
    client = SetupClient()
    wallet = FlashWalletExecutor(client, slippage_percentage=Decimal("0.5"))
    monkeypatch.setattr("tick_mvp.venues.flash.wallet.time.sleep", lambda _seconds: None)
    secret = "0x" + "01" * 32

    first = wallet.prepare_wallet(secret, Decimal("10"))
    second = wallet.prepare_wallet(secret, Decimal("10"))

    assert first["allowanceReady"] is True
    assert first["delegationReady"] is True
    assert Decimal(first["collateralBalanceUsd"]) == Decimal("10")
    assert first["setupSubmitted"] is True
    assert second["setupSubmitted"] is False
    assert wallet.collateral_balance_usd(secret) == Decimal("10")
    assert client.paths == [
        "/transaction-builder/init-basket",
        "/transaction-builder/init-deposit-ledger",
        "/transaction-builder/delegate-basket",
        "/transaction-builder/deposit-direct",
    ]


def test_flash_wallet_waits_for_usdc_before_platform_sol(monkeypatch) -> None:
    client = SetupClient()
    funder = SetupFunder()
    wallet = FlashWalletExecutor(
        client,
        slippage_percentage=Decimal("0.5"),
        setup_funder=funder,
    )
    monkeypatch.setattr("tick_mvp.venues.flash.wallet.time.sleep", lambda _seconds: None)

    result = wallet.prepare_wallet("0x" + "01" * 32, Decimal("10"))

    assert result["setupStatus"] == "awaiting_usdc"
    assert result["allowanceReady"] is False
    assert funder.targets == []
    assert client.paths == []


def test_flash_wallet_platform_funds_setup_and_deposits_all_usdc(monkeypatch) -> None:
    client = SetupClient()
    funder = SetupFunder(usdc=Decimal("12.5"))
    wallet = FlashWalletExecutor(
        client,
        slippage_percentage=Decimal("0.5"),
        setup_funder=funder,
    )
    monkeypatch.setattr("tick_mvp.venues.flash.wallet.time.sleep", lambda _seconds: None)

    result = wallet.prepare_wallet("0x" + "01" * 32, Decimal("10"))

    assert result["setupStatus"] == "ready"
    assert result["allowanceReady"] is True
    assert Decimal(result["collateralBalanceUsd"]) == Decimal("12.5")
    assert funder.targets == [Decimal("0.075")]
    assert client.available == Decimal("12.5")
    assert any(
        item["builderPath"] == "/transaction-builder/deposit-direct"
        for item in result["setupTransactions"]
    )


def test_flash_wallet_later_deposit_uses_operational_sol_target(monkeypatch) -> None:
    client = SetupClient()
    client.basket = "basket"
    client.available = Decimal("5")
    client.delegated = True
    funder = SetupFunder(usdc=Decimal("7"))
    wallet = FlashWalletExecutor(
        client,
        slippage_percentage=Decimal("0.5"),
        setup_funder=funder,
    )
    monkeypatch.setattr("tick_mvp.venues.flash.wallet.time.sleep", lambda _seconds: None)

    result = wallet.prepare_wallet("0x" + "01" * 32, Decimal("10"))

    assert Decimal(result["collateralBalanceUsd"]) == Decimal("12")
    assert funder.targets == [Decimal("0.005")]
    assert client.paths == ["/transaction-builder/deposit-direct"]


def test_flash_wallet_accepts_existing_deposit_ledger_collateral(monkeypatch) -> None:
    client = SetupClient()
    client.basket = "basket"
    client.delegated = True
    funder = SetupFunder(deposited_usdc=Decimal("15"))
    wallet = FlashWalletExecutor(
        client,
        slippage_percentage=Decimal("0.5"),
        setup_funder=funder,
    )
    monkeypatch.setattr("tick_mvp.venues.flash.wallet.time.sleep", lambda _seconds: None)

    result = wallet.prepare_wallet("0x" + "01" * 32, Decimal("10"))

    assert result["allowanceReady"] is True
    assert result["delegationReady"] is True
    assert Decimal(result["collateralBalanceUsd"]) == Decimal("15")
    assert result["setupSubmitted"] is False
    assert client.paths == []
