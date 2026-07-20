#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from typing import Any

import requests


FAPI_HOST = "https://fapi.asterdex.com"
FAPI3_HOST = "https://fapi3.asterdex.com"
ASTER_RPC = "https://tapi.asterdex.com/info"


@dataclass(frozen=True)
class ProbeResult:
    name: str
    ok: bool
    elapsed_ms: float
    detail: Any


def request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    retries: int,
    timeout: float,
) -> tuple[Any, float]:
    errors: list[str] = []
    for attempt in range(1, retries + 1):
        started = time.perf_counter()
        try:
            response = session.request(
                method,
                url,
                params=params,
                json=body,
                timeout=timeout,
                headers={"user-agent": "tick-venue-probe/0.1"},
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            if response.status_code >= 400:
                snippet = response.text.replace("\n", " ")[:220]
                raise RuntimeError(f"HTTP {response.status_code}: {snippet}")
            return response.json(), elapsed_ms
        except Exception as exc:  # noqa: BLE001 - probe should report all transport errors.
            errors.append(f"attempt {attempt}: {exc}")
            if attempt < retries:
                time.sleep(min(0.25 * attempt, 2.0))
    raise RuntimeError("; ".join(errors))


def probe(
    name: str,
    session: requests.Session,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    retries: int,
    timeout: float,
) -> ProbeResult:
    started = time.perf_counter()
    try:
        payload, elapsed_ms = request_json(
            session,
            method,
            url,
            params=params,
            body=body,
            retries=retries,
            timeout=timeout,
        )
        return ProbeResult(name=name, ok=True, elapsed_ms=elapsed_ms, detail=payload)
    except Exception as exc:  # noqa: BLE001 - probe should continue through failures.
        return ProbeResult(
            name=name,
            ok=False,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            detail=str(exc),
        )


def slim_result(result: ProbeResult) -> dict[str, Any]:
    detail = result.detail
    if result.name == "depth" and result.ok:
        detail = {
            "lastUpdateId": detail.get("lastUpdateId"),
            "bestBid": detail.get("bids", [["", ""]])[0],
            "bestAsk": detail.get("asks", [["", ""]])[0],
        }
    return asdict(ProbeResult(result.name, result.ok, round(result.elapsed_ms, 1), detail))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke-test Aster public V3 market data and Aster Chain RPC."
    )
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=12)
    parser.add_argument(
        "--check-fapi3",
        action="store_true",
        help="Also probe fapi3.asterdex.com to show whether it is still blocked.",
    )
    parser.add_argument(
        "--exchange-info",
        action="store_true",
        help="Fetch the large exchangeInfo payload and summarize the requested symbol.",
    )
    args = parser.parse_args()

    session = requests.Session()
    symbol = args.symbol.upper()

    probes = [
        probe(
            "ping",
            session,
            "GET",
            f"{FAPI_HOST}/fapi/v3/ping",
            retries=args.retries,
            timeout=args.timeout,
        ),
        probe(
            "bookTicker",
            session,
            "GET",
            f"{FAPI_HOST}/fapi/v3/ticker/bookTicker",
            params={"symbol": symbol},
            retries=args.retries,
            timeout=args.timeout,
        ),
        probe(
            "depth",
            session,
            "GET",
            f"{FAPI_HOST}/fapi/v3/depth",
            params={"symbol": symbol, "limit": 5},
            retries=args.retries,
            timeout=args.timeout,
        ),
        probe(
            "premiumIndex",
            session,
            "GET",
            f"{FAPI_HOST}/fapi/v3/premiumIndex",
            params={"symbol": symbol},
            retries=args.retries,
            timeout=args.timeout,
        ),
        probe(
            "ticker24h",
            session,
            "GET",
            f"{FAPI_HOST}/fapi/v3/ticker/24hr",
            params={"symbol": symbol},
            retries=args.retries,
            timeout=args.timeout,
        ),
        probe(
            "asterChainRpc",
            session,
            "POST",
            ASTER_RPC,
            body={
                "jsonrpc": "2.0",
                "method": "aster_getBalance",
                "params": ["0x0000000000000000000000000000000000000000", "latest"],
                "id": 1,
            },
            retries=args.retries,
            timeout=args.timeout,
        ),
    ]

    if args.check_fapi3:
        probes.append(
            probe(
                "fapi3Ping",
                session,
                "GET",
                f"{FAPI3_HOST}/fapi/v3/ping",
                retries=1,
                timeout=args.timeout,
            )
        )

    if args.exchange_info:
        exchange = probe(
            "exchangeInfo",
            session,
            "GET",
            f"{FAPI_HOST}/fapi/v3/exchangeInfo",
            retries=args.retries,
            timeout=args.timeout,
        )
        if exchange.ok:
            match = next(
                (
                    item
                    for item in exchange.detail.get("symbols", [])
                    if item.get("symbol") == symbol
                ),
                None,
            )
            exchange = ProbeResult(
                name="exchangeInfo",
                ok=match is not None,
                elapsed_ms=exchange.elapsed_ms,
                detail=match or f"symbol not found: {symbol}",
            )
        probes.append(exchange)

    print(json.dumps([slim_result(item) for item in probes], indent=2))


if __name__ == "__main__":
    main()
