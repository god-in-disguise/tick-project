from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class AvantisPair:
    market: str
    symbol: str
    name: str
    asset_class: str
    pair_index: int
    lazer_feed_id: int
    min_leverage: Decimal
    max_leverage: Decimal
    min_notional_usd: Decimal
    pnl_spread_pct: Decimal
    spread_pct: Decimal
    profit_fee_tiers: tuple[tuple[Decimal, Decimal], ...]
    market_open: bool
    feed_stable: bool

    @property
    def min_collateral_usd(self) -> Decimal:
        if self.max_leverage <= 0:
            return self.min_notional_usd
        return self.min_notional_usd / self.max_leverage


def parse_zfp_catalog(payload: dict[str, Any]) -> dict[str, AvantisPair]:
    raw_pairs = payload.get("pairInfos") or {}
    items = raw_pairs.items() if isinstance(raw_pairs, dict) else enumerate(raw_pairs)
    result: dict[str, AvantisPair] = {}
    for raw_index, row in items:
        if not isinstance(row, dict):
            continue
        storage = row.get("storagePairParams") or {}
        leverages = row.get("leverages") or {}
        lazer = row.get("lazerFeed") or {}
        if int(storage.get("isPnlTypeAllowed") or 0) != 1:
            continue
        source = str(row.get("from") or "").strip().upper()
        target = str(row.get("to") or "").strip().upper()
        feed_id = lazer.get("feedId") or storage.get("lazerFeedId")
        if not source or not target or feed_id is None:
            continue
        market = f"AVANTIS-{source}-{target}"
        attributes = ((row.get("feed") or {}).get("attributes") or {})
        pnl_fees = row.get("pnlFees") or {}
        tier_thresholds = pnl_fees.get("tierP") or []
        fee_shares = pnl_fees.get("feesP") or []
        result[market] = AvantisPair(
            market=market,
            symbol=_symbol(source, target),
            name=_name(source, target),
            asset_class=_asset_class(attributes, source),
            pair_index=int(row.get("index", raw_index)),
            lazer_feed_id=int(feed_id),
            min_leverage=Decimal(str(leverages.get("pnlMinLeverage") or 1)),
            max_leverage=Decimal(str(leverages.get("pnlMaxLeverage") or 1)),
            min_notional_usd=Decimal(str(row.get("minLevPosUSDC") or 0)),
            pnl_spread_pct=Decimal(str(row.get("pnlSpreadP") or 0)),
            spread_pct=Decimal(str(row.get("spreadP") or 0)),
            profit_fee_tiers=_profit_fee_tiers(tier_thresholds, fee_shares),
            market_open=bool(attributes.get("isOpen", attributes.get("is_open", True))),
            feed_stable=str(lazer.get("state") or "").lower() == "stable",
        )
    return result


def market_pair(catalog: dict[str, AvantisPair], market: str) -> AvantisPair:
    normalized = market.strip().upper()
    try:
        return catalog[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported Avantis market: {market}") from exc


def _symbol(source: str, target: str) -> str:
    return source if target == "USD" else f"{source}{target}"


def _name(source: str, target: str) -> str:
    names = {
        "BTC": "Bitcoin",
        "ETH": "Ethereum",
        "SOL": "Solana",
        "XAU": "Gold",
        "XAG": "Silver",
    }
    if target == "USD" and source in names:
        return names[source]
    return f"{source} / {target}"


def _asset_class(attributes: dict[str, Any], source: str) -> str:
    raw = str(attributes.get("asset_type") or "").lower()
    if raw == "crypto":
        return "crypto"
    if source in {"XAU", "XAG"}:
        return "commodity"
    return "forex"


def _profit_fee_tiers(
    thresholds: list[Any],
    shares: list[Any],
) -> tuple[tuple[Decimal, Decimal], ...]:
    if not shares:
        return ()
    tiers = [(Decimal(0), Decimal(str(shares[0])))]
    tiers.extend(
        (Decimal(str(thresholds[index - 1])), Decimal(str(shares[index])))
        for index in range(1, min(len(thresholds), len(shares)))
    )
    return tuple(tiers)
