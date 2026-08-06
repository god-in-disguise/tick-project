from datetime import UTC, datetime
from decimal import Decimal

from tick_mvp.core.config import Settings
from tick_mvp.domain.states import PositionStatus, TradeSide
from tick_mvp.venues.avantis.adapter import AvantisVenue
from tick_mvp.venues.avantis.catalog import AvantisPair, parse_zfp_catalog
from tick_mvp.venues.avantis.pricing import normalize_open_quote
from tick_mvp.venues.avantis.runtime import AvantisExecution, _terminal_event
from tick_mvp.venues.base import VenueTxResult


BTC = AvantisPair(
    market="AVANTIS-BTC-USD",
    symbol="BTC",
    name="Bitcoin",
    asset_class="crypto",
    pair_index=1,
    lazer_feed_id=1,
    min_leverage=Decimal("75"),
    max_leverage=Decimal("500"),
    min_notional_usd=Decimal("100"),
    pnl_spread_pct=Decimal("0.02"),
    spread_pct=Decimal(0),
    profit_fee_tiers=(
        (Decimal("0"), Decimal("80")),
        (Decimal("1"), Decimal("50")),
        (Decimal("5"), Decimal("45")),
    ),
    market_open=True,
    feed_stable=True,
)


def test_avantis_catalog_keeps_only_live_zfp_pairs() -> None:
    catalog = parse_zfp_catalog(
        {
            "pairInfos": {
                "1": {
                    "index": 1,
                    "from": "BTC",
                    "to": "USD",
                    "minLevPosUSDC": 100,
                    "pnlSpreadP": 0.02,
                    "pnlFees": {
                        "tierP": [1, 5, 25],
                        "feesP": [80, 50, 45],
                    },
                    "storagePairParams": {"isPnlTypeAllowed": 1},
                    "leverages": {"pnlMinLeverage": 75, "pnlMaxLeverage": 500},
                    "lazerFeed": {"feedId": 1, "state": "stable"},
                    "feed": {"attributes": {"asset_type": "crypto", "isOpen": True}},
                },
                "2": {
                    "index": 2,
                    "from": "DOGE",
                    "to": "USD",
                    "storagePairParams": {"isPnlTypeAllowed": 0},
                },
            }
        }
    )

    assert list(catalog) == ["AVANTIS-BTC-USD"]
    assert catalog["AVANTIS-BTC-USD"].min_collateral_usd == Decimal("0.2")
    assert catalog["AVANTIS-BTC-USD"].profit_fee_tiers[1] == (
        Decimal("1"),
        Decimal("50"),
    )


def test_avantis_quote_uses_zfp_opening_adjustment_and_live_limits() -> None:
    quote = normalize_open_quote(
        BTC,
        price=Decimal("100000"),
        side=TradeSide.LONG,
        ticket_usd=Decimal("10"),
        leverage=Decimal("500"),
        max_loss_usd=None,
        take_profit_usd=None,
        execution_enabled=True,
    )

    assert quote.notional_usd == Decimal("5000")
    assert quote.estimated_open_cost_usd == Decimal("1")
    assert quote.estimated_close_cost_usd == Decimal(0)
    assert quote.opening_allowed is True
    assert quote.payload["winningCloseFee"] == "variable_profit_share"
    assert quote.payload["profitFeeTiers"][0] == {
        "minProfitPct": "0",
        "feeSharePct": "80",
    }


class FakeRuntime:
    def catalog(self):
        return {BTC.market: BTC}

    def price(self, pair):
        assert pair == BTC
        return Decimal("100000")

    def open_position(self, **kwargs):
        assert kwargs["market"] == BTC.market
        return AvantisExecution(
            tx=_tx(),
            callback={
                "event": "MarketExecuted",
                "source": "base_pendingLogs",
                "transactionHash": "0x" + "22" * 32,
                "args": {
                    "open": True,
                    "price": 1_000_000_000_000_000,
                    "t": {
                        "trader": "0x" + "11" * 20,
                        "pairIndex": 1,
                        "index": 3,
                        "openPrice": 1_000_000_000_000_000,
                        "leverage": 5_000_000_000_000,
                        "sl": 0,
                        "tp": 0,
                        "timestamp": int(datetime.now(UTC).timestamp()),
                    },
                },
            },
            account_balance_before_usd=Decimal("50"),
        )

    def close_position(self, **kwargs):
        assert kwargs["venue_position_id"] == "1:3"
        return AvantisExecution(
            tx=_tx(),
            callback={
                "event": "MarketExecuted",
                "source": "base_pendingLogs",
                "transactionHash": "0x" + "33" * 32,
                "args": {
                    "open": False,
                    "price": 1_000_100_000_000_000,
                    "usdcSentToTrader": 11_250_000,
                    "t": {"pairIndex": 1, "index": 3, "initialPosToken": 10_000_000},
                },
            },
        )


def test_avantis_adapter_normalizes_callback_truth() -> None:
    venue = AvantisVenue(
        Settings(avantis_real_execution_enabled=True),
        runtime=FakeRuntime(),
    )

    opened = venue.open_position(
        private_key_hex="0x" + "01" * 32,
        market=BTC.market,
        side=TradeSide.LONG,
        ticket_usd=Decimal("10"),
        leverage=Decimal("500"),
        quote_payload={},
        stop_loss_price=None,
        take_profit_price=None,
    )
    closed = venue.close_position(
        private_key_hex="0x" + "01" * 32,
        market=BTC.market,
        side=TradeSide.LONG,
        venue_position_id=opened.venue_position_id,
    )

    assert opened.venue_position_id == "1:3"
    assert opened.entry_price == Decimal("100000")
    assert closed.close_cashflow_usd == Decimal("11.25")
    assert closed.venue_realized_pnl_usd == Decimal("1.25")
    assert closed.payload["detectionSource"] == "base_pendingLogs"


def test_avantis_limit_callback_classifies_tp_sl_and_liquidation() -> None:
    reasons = {0: "take_profit", 1: "stop_loss", 2: "liquidation"}
    for order_type, expected in reasons.items():
        event = _terminal_event(
            {
                "event": "LimitExecuted",
                "source": "base_pendingLogs",
                "receivedAt": 1_784_000_000,
                "transactionHash": "0x" + "55" * 32,
                "blockNumber": 100,
                "logIndex": order_type,
                "args": {
                    "orderType": order_type,
                    "usdcSentToTrader": 2_500_000,
                    "t": {
                        "trader": "0x" + "11" * 20,
                        "pairIndex": 1,
                        "index": 3,
                    },
                },
            }
        )

        assert event is not None
        assert event.reason == expected
        assert event.returned_collateral_usd == Decimal("2.5")
        assert event.status == (
            PositionStatus.LIQUIDATED
            if expected == "liquidation"
            else PositionStatus.CLOSED
        )


def test_avantis_market_close_callback_is_manual_close() -> None:
    event = _terminal_event(
        {
            "event": "MarketExecuted",
            "source": "base_logs",
            "receivedAt": 1_784_000_000,
            "args": {
                "open": False,
                "usdcSentToTrader": 9_000_000,
                "t": {
                    "trader": "0x" + "11" * 20,
                    "pairIndex": 1,
                    "index": 3,
                },
            },
        }
    )

    assert event is not None
    assert event.reason == "manual_close"
    assert event.venue_position_id == "1:3"


def _tx() -> VenueTxResult:
    return VenueTxResult(
        status="confirmed",
        tx_hash="0x" + "aa" * 32,
        nonce=1,
        block_number=1,
        gas_used=100_000,
        effective_gas_price=1_000_000,
        payload={"gasPayer": "0x" + "44" * 20, "valueWei": 5_615_000_000_000},
    )
