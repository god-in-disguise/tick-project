from decimal import Decimal

from tick_mvp.domain.states import TradeSide
from tick_mvp.venues.gtrade.pricing import estimate_open
from tick_mvp.venues.gtrade.public import GTradePair


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
    )

    quote = estimate_open(
        pair,
        {"mid": Decimal("100"), "bid": Decimal("100"), "ask": Decimal("100"), "isMarketOpen": True},
        TradeSide.LONG,
        ticket_usd=Decimal("10"),
        requested_leverage=Decimal("100"),
        max_loss_usd=Decimal("10"),
    )

    assert quote.leverage == Decimal("500")
    assert quote.notional_usd == Decimal("5000")
    assert quote.estimated_open_cost_usd == Decimal("1.0000")
    assert quote.estimated_close_cost_usd == Decimal("1.0000")
    assert quote.estimated_round_trip_cost_usd == Decimal("2.0000")
    assert quote.stop_loss_price == Decimal("99.800")
    assert quote.payload["leverageNormalized"] is True

