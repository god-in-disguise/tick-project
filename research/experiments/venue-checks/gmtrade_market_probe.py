#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

import websockets


GMTRADE_WS_URL = "wss://gmtrade-web-backend.gmtrade.xyz/ws"
PROTOCOL_SCALE = Decimal(10) ** 20


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    max_leverage: Decimal
    pools: int
    long_open_interest_usd: Decimal
    short_open_interest_usd: Decimal
    long_oi_headroom_usd: Decimal
    short_oi_headroom_usd: Decimal
    long_to_short_liquidity_usd: Decimal
    short_to_long_liquidity_usd: Decimal
    gt_enabled: bool


def scaled(value: Any) -> Decimal:
    return Decimal(str(value or 0)) / PROTOCOL_SCALE


def sum_scaled(items: list[dict[str, Any]], key: str) -> Decimal:
    return sum((scaled(item.get(key)) for item in items), Decimal(0))


def oi_headroom(items: list[dict[str, Any]], side: str) -> Decimal:
    current_key = f"openInterestFor{side}"
    max_key = f"maxOpenInterestFor{side}"
    return sum(
        (
            max(
                Decimal(0),
                scaled(item.get(max_key)) - scaled(item.get(current_key)),
            )
            for item in items
        ),
        Decimal(0),
    )


def parse_market(item: dict[str, Any]) -> MarketSnapshot:
    pools = item.get("marketInfos") or []
    return MarketSnapshot(
        symbol=str(item["symbol"]),
        max_leverage=scaled(item.get("maxLeverage")),
        pools=len(pools),
        long_open_interest_usd=sum_scaled(pools, "openInterestForLong"),
        short_open_interest_usd=sum_scaled(pools, "openInterestForShort"),
        long_oi_headroom_usd=oi_headroom(pools, "Long"),
        short_oi_headroom_usd=oi_headroom(pools, "Short"),
        long_to_short_liquidity_usd=sum_scaled(
            pools, "longToShortAvailableLiquidity"
        ),
        short_to_long_liquidity_usd=sum_scaled(
            pools, "shortToLongAvailableLiquidity"
        ),
        gt_enabled=bool(item.get("gtEnabled")),
    )


async def fetch_market_items(timeout_seconds: float) -> list[dict[str, Any]]:
    async with websockets.connect(
        GMTRADE_WS_URL,
        origin="https://gmtrade.xyz",
        user_agent_header="Mozilla/5.0",
        open_timeout=timeout_seconds,
        ping_interval=20,
        compression=None,
    ) as socket:
        await socket.send(json.dumps({"subscribe": "indexTokens"}))
        while True:
            raw = await asyncio.wait_for(socket.recv(), timeout_seconds)
            message = json.loads(raw)
            if message.get("type") == "indexTokens":
                return message["payload"]


async def fetch_markets(timeout_seconds: float) -> list[MarketSnapshot]:
    return [
        parse_market(item) for item in await fetch_market_items(timeout_seconds)
    ]


def money(value: Decimal) -> str:
    return f"${value:,.0f}"


def decimal_json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Unsupported JSON value: {type(value)!r}")


def print_table(markets: list[MarketSnapshot]) -> None:
    print(f"markets: {len(markets)}")
    print(
        "leverage\tsymbol\tpools\tlong OI\tshort OI\t"
        "long OI headroom\tshort OI headroom\t"
        "long->short liquidity\tshort->long liquidity\tGT"
    )
    for market in markets:
        print(
            f"{market.max_leverage:g}x\t"
            f"{market.symbol}\t"
            f"{market.pools}\t"
            f"{money(market.long_open_interest_usd)}\t"
            f"{money(market.short_open_interest_usd)}\t"
            f"{money(market.long_oi_headroom_usd)}\t"
            f"{money(market.short_oi_headroom_usd)}\t"
            f"{money(market.long_to_short_liquidity_usd)}\t"
            f"{money(market.short_to_long_liquidity_usd)}\t"
            f"{market.gt_enabled}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read GMTrade's public live leverage and capacity feed."
    )
    parser.add_argument("--min-leverage", type=Decimal, default=Decimal(0))
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--raw-symbol",
        help="Print one unmodified market payload for connector research.",
    )
    args = parser.parse_args()

    if args.raw_symbol:
        items = asyncio.run(fetch_market_items(args.timeout))
        symbol = args.raw_symbol.upper()
        item = next(
            (candidate for candidate in items if candidate.get("symbol") == symbol),
            None,
        )
        if item is None:
            raise SystemExit(f"market not found: {symbol}")
        print(json.dumps(item, indent=2))
        return

    markets = asyncio.run(fetch_markets(args.timeout))
    markets = sorted(
        (market for market in markets if market.max_leverage >= args.min_leverage),
        key=lambda market: (-market.max_leverage, market.symbol),
    )

    if args.json:
        print(json.dumps([asdict(market) for market in markets], default=decimal_json))
    else:
        print_table(markets)


if __name__ == "__main__":
    main()
