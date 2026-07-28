from decimal import Decimal

from tick_mvp.infrastructure.market_history import PriceBar


def test_price_bar_preserves_real_ohlc_and_sample_count() -> None:
    bar = PriceBar.from_tick(
        {
            "venue": "gtrade",
            "market": "ETHDEGEN-USD",
            "receivedAt": 1_000.1,
            "price": "3500.10",
            "sequence": 10,
            "source": "gtrade_pricing_ws",
        }
    )
    bar.add(
        {
            "price": "3501.25",
            "sequence": 11,
        }
    )
    bar.add(
        {
            "price": "3499.75",
            "sequence": 12,
        }
    )

    assert bar.open == Decimal("3500.10")
    assert bar.high == Decimal("3501.25")
    assert bar.low == Decimal("3499.75")
    assert bar.close == Decimal("3499.75")
    assert bar.sample_count == 3
    assert bar.first_sequence == 10
    assert bar.last_sequence == 12
