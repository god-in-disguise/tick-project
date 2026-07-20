#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from statistics import mean
from typing import Any


MAX_ITERATIONS = 5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Human-triggered repeated GMTrade live canary runner."
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--i-understand-live-risk", action="store_true")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--hold-seconds", type=float, default=3)
    parser.add_argument("--side-mode", choices=("long", "short", "alternate"), default="alternate")
    parser.add_argument("--priority-lamports", type=int, default=25_000)
    parser.add_argument("--skip-preflight", action="store_true")
    parser.add_argument("--max-price-age", type=float, default=10)
    parser.add_argument("--max-quote-age-at-submit", type=float, default=5)
    parser.add_argument("--max-quote-drift-bps", default="10")
    parser.add_argument("--out-dir", type=Path, default=Path("venue-checks/reports/gmtrade"))
    return parser.parse_args()


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def field(report: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = report
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def side_for(index: int, mode: str) -> str:
    if mode == "alternate":
        return "long" if index % 2 == 0 else "short"
    return mode


def summarize(reports: list[dict[str, Any]]) -> dict[str, Any]:
    def numbers(path: tuple[str, ...]) -> list[Decimal]:
        values = [decimal_or_none(field(report, path)) for report in reports]
        return [value for value in values if value is not None]

    def average(path: tuple[str, ...]) -> str | None:
        values = numbers(path)
        if not values:
            return None
        return str(mean(values))

    sol_deltas = numbers(("balanceDelta", "sol"))
    usdc_deltas = numbers(("balanceDelta", "usdc"))
    return {
        "runs": len(reports),
        "avgOpenRequestMs": average(("openRequest", "requestConfirmationMs")),
        "avgOpenEndToEndMs": average(("openRequest", "endToEndMs")),
        "avgStopRequestMs": average(("stopRequest", "requestConfirmationMs")),
        "avgCloseRequestMs": average(("closeRequest", "requestConfirmationMs")),
        "avgCloseEndToEndMs": average(("closeRequest", "endToEndMs")),
        "totalSolDelta": str(sum(sol_deltas, Decimal(0))),
        "totalUsdcDelta": str(sum(usdc_deltas, Decimal(0))),
        "finalPositions": [report.get("finalPositions") for report in reports],
        "finalOrders": [report.get("finalOrders") for report in reports],
    }


def main() -> None:
    args = parse_args()
    if not args.execute:
        print("Dry run only. Add --execute --i-understand-live-risk to run live.")
        return
    if not args.i_understand_live_risk:
        raise SystemExit("--i-understand-live-risk is required for repeat live canaries")
    if args.iterations < 1 or args.iterations > MAX_ITERATIONS:
        raise SystemExit(f"iterations must be between 1 and {MAX_ITERATIONS}")
    if args.hold_seconds < 0 or args.hold_seconds > 10:
        raise SystemExit("hold-seconds must be between 0 and 10")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.out_dir / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    reports: list[dict[str, Any]] = []
    script = Path(__file__).with_name("gmtrade_user_canary.py")

    for index in range(args.iterations):
        side = side_for(index, args.side_mode)
        report_path = run_dir / f"gmtrade_canary_{index + 1:02d}_{side}.json"
        command = [
            sys.executable,
            str(script),
            "--execute",
            "--runner-confirmed",
            "--side",
            side,
            "--hold-seconds",
            str(args.hold_seconds),
            "--submit-mode",
            "direct-rpc",
            "--priority-lamports",
            str(args.priority_lamports),
            "--max-price-age",
            str(args.max_price_age),
            "--max-quote-age-at-submit",
            str(args.max_quote_age_at_submit),
            "--max-quote-drift-bps",
            str(args.max_quote_drift_bps),
            "--json-report",
            str(report_path),
        ]
        if args.skip_preflight:
            command.append("--skip-preflight")
        print(f"\nRun {index + 1}/{args.iterations}: {side}")
        started = time.perf_counter()
        result = subprocess.run(
            command,
            text=True,
            check=False,
        )
        if result.returncode:
            raise SystemExit(f"Run {index + 1} failed with exit code {result.returncode}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["repeatRunnerElapsedMs"] = round((time.perf_counter() - started) * 1000, 1)
        reports.append(report)
        time.sleep(1)

    summary = summarize(reports)
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("\nSummary")
    print(json.dumps(summary, indent=2))
    print(f"Reports: {run_dir}")


if __name__ == "__main__":
    main()
