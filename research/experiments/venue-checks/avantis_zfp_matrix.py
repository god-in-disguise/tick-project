#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an Avantis ZFP latency and cost matrix from canary reports."
    )
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--json-report", type=Path)
    parser.add_argument("--markdown-report", type=Path)
    return parser.parse_args()


def elapsed(timeline: dict[str, Any], name: str) -> float:
    return float(timeline[name]["elapsedMs"])


def closing_fee_usdc(report: dict[str, Any]) -> float:
    events = report["costAnalysis"]["close"]["feesCharged"]
    return sum(int(event["closingFee"]) for event in events) / 10**6


def row_from_report(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text())
    timeline = report["timeline"]
    open_gesture = elapsed(timeline, "open_gesture")
    close_gesture = elapsed(timeline, "close_gesture")
    adjustment = float(report["costAnalysis"]["totalExecutionAdjustmentUsd"])
    fee = closing_fee_usdc(report)
    usdc_delta = float(report["usdcDelta"])

    return {
        "report": str(path),
        "leverage": int(report["leverage"]),
        "side": report["side"],
        "marginUsdc": float(report["marginUsdc"]),
        "setupMs": float(report["setupMs"]),
        "openEncodeSignMs": elapsed(timeline, "open_signed") - open_gesture,
        "openBroadcastResponseMs": elapsed(timeline, "open_broadcast_returned")
        - elapsed(timeline, "open_broadcast_started"),
        "openInitiationPreconfirmedMs": elapsed(timeline, "open_receipt")
        - open_gesture,
        "openVisibleMs": elapsed(timeline, "open_callback_direct") - open_gesture,
        "openKeeperAfterInitiationMs": elapsed(timeline, "open_callback_direct")
        - elapsed(timeline, "open_receipt"),
        "closeEncodeSignMs": elapsed(timeline, "close_signed") - close_gesture,
        "closeBroadcastResponseMs": elapsed(timeline, "close_broadcast_returned")
        - elapsed(timeline, "close_broadcast_started"),
        "closeInitiationPreconfirmedMs": elapsed(timeline, "close_receipt")
        - close_gesture,
        "closeVisibleMs": elapsed(timeline, "close_callback_direct") - close_gesture,
        "closeKeeperAfterInitiationMs": elapsed(timeline, "close_callback_direct")
        - elapsed(timeline, "close_receipt"),
        "closeSealAfterVisibleMs": elapsed(timeline, "close_callback_sealed")
        - elapsed(timeline, "close_callback_direct"),
        "executionAdjustmentUsd": adjustment,
        "executionAdjustmentPctOfMargin": adjustment
        / float(report["marginUsdc"])
        * 100,
        "closingFeeUsdc": fee,
        "marketAndRoundingResultUsdc": usdc_delta + adjustment + fee,
        "actualUsdcDelta": usdc_delta,
        "returnedUsdc": float(report["marginUsdc"]) + usdc_delta,
        "ethDelta": float(report["ethDelta"]),
    }


def metric_summary(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    values = [float(row[key]) for row in rows]
    return {
        "min": min(values),
        "median": statistics.median(values),
        "max": max(values),
    }


def build_matrix(paths: list[Path]) -> dict[str, Any]:
    rows = sorted((row_from_report(path) for path in paths), key=lambda row: row["leverage"])
    metrics = [
        "openEncodeSignMs",
        "openBroadcastResponseMs",
        "openInitiationPreconfirmedMs",
        "openVisibleMs",
        "openKeeperAfterInitiationMs",
        "closeEncodeSignMs",
        "closeBroadcastResponseMs",
        "closeInitiationPreconfirmedMs",
        "closeVisibleMs",
        "closeKeeperAfterInitiationMs",
        "closeSealAfterVisibleMs",
    ]
    return {
        "sampleCount": len(rows),
        "method": "prewarmed Pyth Lazer SSE + local calldata/signing + reused QuickNode HTTP + Base Flashblocks pendingLogs",
        "p95Available": len(rows) >= 20,
        "rows": rows,
        "latencySummaryMs": {key: metric_summary(rows, key) for key in metrics},
    }


def markdown(matrix: dict[str, Any]) -> str:
    lines = [
        "# Avantis ZFP Optimized Matrix",
        "",
        f"Samples: {matrix['sampleCount']}. Each sample used $10 BTC/USD ZFP with a one-second hold.",
        "",
        "| Leverage | Side | Open preconfirm | Open visible | Close preconfirm | Close visible | Seal after visible | Execution adjustment | Closing fee | Actual result |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in matrix["rows"]:
        lines.append(
            f"| {row['leverage']}x | {row['side']} | "
            f"{row['openInitiationPreconfirmedMs']:.1f} ms | "
            f"{row['openVisibleMs'] / 1000:.3f} s | "
            f"{row['closeInitiationPreconfirmedMs']:.1f} ms | "
            f"{row['closeVisibleMs'] / 1000:.3f} s | "
            f"{row['closeSealAfterVisibleMs']:.1f} ms | "
            f"${row['executionAdjustmentUsd']:.6f} | "
            f"${row['closingFeeUsdc']:.6f} | "
            f"${row['actualUsdcDelta']:+.6f} |"
        )
    summary = matrix["latencySummaryMs"]
    lines.extend(
        [
            "",
            "## Cross-Sample Latency",
            "",
            "| Metric | Min | Median | Max |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for key in (
        "openEncodeSignMs",
        "openBroadcastResponseMs",
        "openInitiationPreconfirmedMs",
        "openVisibleMs",
        "closeEncodeSignMs",
        "closeBroadcastResponseMs",
        "closeInitiationPreconfirmedMs",
        "closeVisibleMs",
        "closeSealAfterVisibleMs",
    ):
        item = summary[key]
        lines.append(
            f"| `{key}` | {item['min']:.1f} ms | {item['median']:.1f} ms | {item['max']:.1f} ms |"
        )
    lines.extend(
        [
            "",
            "Four samples are enough for a first matrix, not a p95. At least 20 optimized cycles are required before setting a route SLO.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    matrix = build_matrix(args.reports)
    output = markdown(matrix)
    print(output)
    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(json.dumps(matrix, indent=2) + "\n")
    if args.markdown_report:
        args.markdown_report.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_report.write_text(output)


if __name__ == "__main__":
    main()
