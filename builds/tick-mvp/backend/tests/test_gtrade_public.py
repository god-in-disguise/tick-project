from decimal import Decimal

from tick_mvp.core.config import Settings
from tick_mvp.venues.gtrade import public
from tick_mvp.venues.gtrade.public import GTradePair, GTradePublicClient


def _pair() -> GTradePair:
    return GTradePair(
        pair_index=300,
        pair="BTCDEGEN-USD",
        raw_symbol="BTCDEGEN",
        symbol="BTC",
        name="Bitcoin",
        group="crypto",
        asset_class="crypto",
        max_leverage=Decimal("500"),
        open_fee_pct=Decimal("0.02"),
        min_position_usd=Decimal("10"),
        min_collateral_usd=Decimal("10"),
        spread_pct=Decimal("0"),
    )


def test_expired_pair_metadata_never_blocks_pair_lookup(monkeypatch) -> None:
    client = GTradePublicClient(Settings(gtrade_pairs_ttl_seconds=0))
    client._pairs_by_name = {"BTCDEGEN-USD": _pair()}
    client._pairs_expires_at = 0

    def fail_network(*_args, **_kwargs):
        raise AssertionError("pair lookup must not synchronously refresh metadata")

    monkeypatch.setattr(public, "_get_json", fail_network)

    assert client.pair("BTCDEGEN/USD").pair_index == 300
