from decimal import Decimal

from tick_mvp.domain.states import TradeSide
from tick_mvp.venues.gtrade.pricing import estimate_open
from tick_mvp.venues.gtrade.public import GTradeError, GTradePair


def test_gtrade_quote_uses_venue_costs_and_stop_loss() -> None:
    pair = GTradePair(
        pair_index=300,
        pair="BTCDEGEN-USD",
        raw_symbol="BTCDEGEN",
        symbol="BTC",
        name="Bitcoin",
        group="Crypto",
        asset_class="CRYPTO",
        max_leverage=Decimal("500"),
        open_fee_pct=Decimal("0.02"),
        min_position_usd=Decimal("10"),
        min_collateral_usd=Decimal("0.02"),
        spread_pct=Decimal("0"),
        liquidation_fee_pct=Decimal("10"),
    )

    quote = estimate_open(
        pair,
        {"mid": Decimal("100"), "bid": Decimal("100"), "ask": Decimal("100"), "isMarketOpen": True},
        TradeSide.LONG,
        ticket_usd=Decimal("10"),
        requested_leverage=Decimal("500"),
        max_loss_usd=Decimal("10"),
        take_profit_usd=Decimal("20"),
    )

    assert quote.leverage == Decimal("500")
    assert quote.notional_usd == Decimal("5000")
    assert quote.estimated_open_cost_usd == Decimal("1.0000")
    assert quote.estimated_close_cost_usd == Decimal("1.0000")
    assert quote.estimated_round_trip_cost_usd == Decimal("2.0000")
    assert quote.liquidation_price == Decimal("99.9000")
    assert quote.stop_loss_price == Decimal("99.800")
    assert quote.take_profit_price == Decimal("100.400")
    assert quote.payload["leverageNormalized"] is False


def test_gtrade_quote_can_disable_stop_loss_and_take_profit() -> None:
    pair = GTradePair(
        pair_index=300,
        pair="BTCDEGEN-USD",
        raw_symbol="BTCDEGEN",
        symbol="BTC",
        name="Bitcoin",
        group="Crypto",
        asset_class="CRYPTO",
        max_leverage=Decimal("500"),
        open_fee_pct=Decimal("0.02"),
        min_position_usd=Decimal("10"),
        min_collateral_usd=Decimal("0.02"),
        spread_pct=Decimal("0"),
    )

    quote = estimate_open(
        pair,
        {"mid": Decimal("100"), "bid": Decimal("100"), "ask": Decimal("100"), "isMarketOpen": True},
        TradeSide.SHORT,
        ticket_usd=Decimal("10"),
        requested_leverage=Decimal("500"),
        max_loss_usd=None,
        take_profit_usd=None,
    )

    assert quote.stop_loss_price is None
    assert quote.take_profit_price is None


def test_gtrade_degen_pair_rejects_non_fixed_leverage() -> None:
    pair = GTradePair(
        pair_index=300,
        pair="BTCDEGEN-USD",
        raw_symbol="BTCDEGEN",
        symbol="BTC",
        name="Bitcoin",
        group="Crypto",
        asset_class="CRYPTO",
        max_leverage=Decimal("500"),
        open_fee_pct=Decimal("0.02"),
        min_position_usd=Decimal("10"),
        min_collateral_usd=Decimal("0.02"),
        spread_pct=Decimal("0"),
    )

    try:
        estimate_open(
            pair,
            {"mid": Decimal("100"), "bid": Decimal("100"), "ask": Decimal("100"), "isMarketOpen": True},
            TradeSide.LONG,
            ticket_usd=Decimal("10"),
            requested_leverage=Decimal("100"),
            max_loss_usd=None,
            take_profit_usd=None,
        )
    except GTradeError as exc:
        assert "only supports 500x" in str(exc)
    else:
        raise AssertionError("expected fixed-leverage rejection")


def test_gtrade_standard_pair_preserves_requested_leverage_and_fee() -> None:
    pair = GTradePair(
        pair_index=0,
        pair="BTC-USD",
        raw_symbol="BTC",
        symbol="BTC",
        name="Bitcoin",
        group="Crypto",
        asset_class="CRYPTO",
        max_leverage=Decimal("200"),
        open_fee_pct=Decimal("0.035"),
        min_position_usd=Decimal("10"),
        min_collateral_usd=Decimal("0.05"),
        spread_pct=Decimal("0"),
    )

    quote = estimate_open(
        pair,
        {"mid": Decimal("65000"), "bid": Decimal("65000"), "ask": Decimal("65000"), "isMarketOpen": True},
        TradeSide.LONG,
        ticket_usd=Decimal("10"),
        requested_leverage=Decimal("100"),
        max_loss_usd=None,
        take_profit_usd=None,
    )

    assert quote.leverage == Decimal("100")
    assert quote.notional_usd == Decimal("1000")
    assert quote.estimated_open_cost_usd == Decimal("0.35000")
