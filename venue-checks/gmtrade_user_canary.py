#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from contextlib import nullcontext
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from solders.pubkey import Pubkey

from gmtrade.config import BTC_USDC_MARKET, SOLANA_USDC_MINT, ProbeConfig
from gmtrade.live_cli import (
    read_actions,
    run_exchange,
    temporary_wallet_file,
)
from gmtrade.live_direct import (
    DirectSubmitResult,
    submit_built_order,
    submit_exchange,
)
from gmtrade.official_cli import build_btc_market_increase, build_exchange_transaction
from gmtrade.quote import (
    QuoteSnapshot,
    fetch_fresh_close_quote,
    fetch_fresh_quote,
    quote_drift_bps,
)
from gmtrade.rpc import SolanaRpc
from gmtrade.transaction import sign_with_blockhash
from gmtrade.wallet import load_keypair


CONFIRMATION = "RUN LIVE GMTRADE CANARY"


def decimal_text(value: Decimal) -> str:
    return format(value, "f")


def wait_for_position(
    config: ProbeConfig,
    owner: str,
    *,
    present: bool,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> tuple[float, object]:
    started = time.perf_counter()
    last: object = []
    while time.perf_counter() - started < timeout_seconds:
        last = read_actions(config, owner, "positions")
        exists = bool(last)
        if exists is present:
            return (time.perf_counter() - started) * 1000, last
        time.sleep(poll_interval_seconds)
    state = "appear" if present else "disappear"
    raise TimeoutError(f"GMTrade position did not {state}: {last}")


def balances(rpc: SolanaRpc, owner: Pubkey) -> dict[str, Decimal]:
    return {
        "sol": Decimal(rpc.balance_lamports(owner)).scaleb(-9),
        "usdc": rpc.token_balance(owner, Pubkey.from_string(SOLANA_USDC_MINT)),
    }


def open_arguments(
    collateral: Decimal,
    leverage: Decimal,
    side: str,
    acceptable_price: Decimal,
) -> list[str]:
    return [
        "market-increase",
        BTC_USDC_MARKET,
        "--collateral-side",
        "short",
        "--initial-collateral-token",
        SOLANA_USDC_MINT,
        "--initial-collateral-token-amount",
        decimal_text(collateral),
        "--side",
        side,
        "--size",
        decimal_text(collateral * leverage),
        "--acceptable-price",
        decimal_text(acceptable_price),
    ]


def stop_arguments(side: str, notional: Decimal, trigger: Decimal) -> list[str]:
    return [
        "stop-loss",
        BTC_USDC_MARKET,
        "--collateral-side",
        "short",
        "--side",
        side,
        "--price",
        decimal_text(trigger),
        "--size",
        decimal_text(notional),
        "--final-output-token",
        SOLANA_USDC_MINT,
    ]


def close_arguments(side: str, notional: Decimal, acceptable: Decimal) -> list[str]:
    return [
        "market-decrease",
        BTC_USDC_MARKET,
        "--collateral-side",
        "short",
        "--side",
        side,
        "--size",
        decimal_text(notional),
        "--final-output-token",
        SOLANA_USDC_MINT,
        "--acceptable-price",
        decimal_text(acceptable),
        "--close-position",
    ]


def direct_report(result: DirectSubmitResult) -> dict[str, Any]:
    return {
        "signature": result.signature,
        "order": result.order,
        "buildMs": round(result.build_ms, 1),
        "signMs": round(result.sign_ms, 1),
        "sendRpcMs": round(result.send_ms, 1),
        "signatureConfirmMs": round(result.confirm_ms, 1),
        "requestConfirmationMs": round(result.elapsed_ms, 1),
        "confirmationSlot": result.confirmation_status.get("slot"),
    }


def cli_report(result: Any) -> dict[str, Any]:
    return {
        "signature": result.signature,
        "order": result.order,
        "requestConfirmationMs": round(result.elapsed_ms, 1),
    }


def quote_report(quote: QuoteSnapshot) -> dict[str, Any]:
    return {
        "referencePrice": str(quote.reference),
        "acceptablePrice": str(quote.acceptable),
        "stopPrice": str(quote.stop),
        "oracleTimestamp": quote.oracle_timestamp,
        "oracleAgeSeconds": round(quote.oracle_age_seconds, 3),
    }


def quote_guard_report(
    request_quote: QuoteSnapshot,
    submit_quote: QuoteSnapshot,
    *,
    max_quote_age_at_submit: float,
    max_quote_drift_bps: Decimal,
) -> dict[str, Any]:
    drift_bps = quote_drift_bps(request_quote, submit_quote)
    quote_to_validation_ms = (
        submit_quote.fetched_monotonic - request_quote.fetched_monotonic
    ) * 1000
    report = {
        "requestQuote": quote_report(request_quote),
        "submitQuote": quote_report(submit_quote),
        "quoteToValidationMs": round(quote_to_validation_ms, 1),
        "driftBps": str(drift_bps.quantize(Decimal("0.0001"))),
        "maxQuoteAgeAtSubmitSeconds": max_quote_age_at_submit,
        "maxQuoteDriftBps": str(max_quote_drift_bps),
    }
    if submit_quote.oracle_age_seconds > max_quote_age_at_submit:
        raise RuntimeError(
            "Quote became stale before submit: "
            f"{submit_quote.oracle_age_seconds:.2f}s > {max_quote_age_at_submit:.2f}s"
        )
    if drift_bps > max_quote_drift_bps:
        raise RuntimeError(
            f"Quote drifted before submit: {drift_bps:.4f} bps > "
            f"{max_quote_drift_bps} bps"
        )
    return report


def submit_exchange_with_quote_guard(
    *,
    config: ProbeConfig,
    rpc: SolanaRpc,
    wallet: Any,
    arguments: list[str],
    request_quote: QuoteSnapshot,
    refresh_quote: Callable[[], QuoteSnapshot],
    max_quote_age_at_submit: float,
    max_quote_drift_bps: Decimal,
    priority_lamports: int | None,
    skip_preflight: bool,
) -> tuple[DirectSubmitResult, dict[str, Any]]:
    build_started = time.perf_counter()
    built = build_exchange_transaction(
        cli_path=config.cli_path,
        rpc_url=config.rpc_url,
        payer=wallet.pubkey(),
        arguments=arguments,
        priority_lamports=priority_lamports,
    )
    build_ms = (time.perf_counter() - build_started) * 1000
    submit_quote = refresh_quote()
    guard = quote_guard_report(
        request_quote,
        submit_quote,
        max_quote_age_at_submit=max_quote_age_at_submit,
        max_quote_drift_bps=max_quote_drift_bps,
    )
    result = submit_built_order(
        rpc,
        wallet,
        built,
        skip_preflight=skip_preflight,
        max_retries=3,
        build_ms=build_ms,
    )
    return result, guard


def main() -> None:
    startup_started = time.perf_counter()
    phase_started = startup_started
    phase_timings: dict[str, float] = {}

    def mark_phase(name: str) -> None:
        nonlocal phase_started
        now = time.perf_counter()
        phase_timings[name] = round((now - phase_started) * 1000, 1)
        phase_started = now

    parser = argparse.ArgumentParser(
        description="Human-confirmed GMTrade open/stop/close canary."
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--runner-confirmed", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--i-understand-live-risk",
        action="store_true",
        help="Skip the interactive live-order confirmation prompt.",
    )
    parser.add_argument("--collateral", type=Decimal, default=Decimal("20"))
    parser.add_argument("--leverage", type=Decimal, default=Decimal("100"))
    parser.add_argument("--side", choices=("long", "short"), default="long")
    parser.add_argument("--hold-seconds", type=float, default=3)
    parser.add_argument("--acceptable-bps", type=Decimal, default=Decimal("30"))
    parser.add_argument("--stop-loss-bps", type=Decimal, default=Decimal("35"))
    parser.add_argument("--max-price-age", type=float, default=10)
    parser.add_argument("--max-quote-age-at-submit", type=float, default=5)
    parser.add_argument("--max-quote-drift-bps", type=Decimal, default=Decimal("10"))
    parser.add_argument(
        "--submit-mode",
        choices=("direct-rpc", "cli"),
        default="direct-rpc",
        help="direct-rpc signs/sends in Python; cli uses the official CLI submit path",
    )
    parser.add_argument(
        "--priority-lamports",
        type=int,
        default=25_000,
        help="GMTrade/Solana priority fee budget for serialized transactions",
    )
    parser.add_argument("--skip-preflight", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=0.2)
    parser.add_argument("--json-report", type=Path)
    args = parser.parse_args()

    if args.collateral != Decimal("20") or args.leverage != Decimal("100"):
        raise SystemExit("This canary is locked to $20 collateral and 100x")
    if args.hold_seconds < 0 or args.hold_seconds > 10:
        raise SystemExit("hold-seconds must be between 0 and 10")

    config = ProbeConfig.from_env()
    wallet = load_keypair(config.private_key)
    rpc = SolanaRpc(config.rpc_url)
    owner = str(wallet.pubkey())
    mark_phase("configuration")
    if read_actions(config, owner, "positions"):
        raise SystemExit("Refusing to start: wallet already has a GMTrade position")
    mark_phase("readPositions")
    if read_actions(config, owner, "orders"):
        raise SystemExit("Refusing to start: wallet already has a GMTrade order")
    mark_phase("readOrders")

    preview_quote = fetch_fresh_quote(
        side=args.side,
        acceptable_bps=args.acceptable_bps,
        stop_loss_bps=args.stop_loss_bps,
        max_age_seconds=args.max_price_age,
    )
    mark_phase("keeperPrice")
    built = build_btc_market_increase(
        cli_path=config.cli_path,
        rpc_url=config.rpc_url,
        payer=wallet.pubkey(),
        collateral_usd=args.collateral,
        leverage=args.leverage,
        side=args.side,
        acceptable_price=preview_quote.acceptable,
        priority_lamports=args.priority_lamports,
    )
    mark_phase("buildOpen")
    transaction = sign_with_blockhash(built.message, rpc.latest_blockhash(), wallet)
    simulation = rpc.simulate(transaction)
    mark_phase("signAndSimulate")
    if simulation.get("err") is not None:
        raise SystemExit(f"Open simulation failed: {simulation['err']}")

    starting_balances = balances(rpc, wallet.pubkey())
    mark_phase("readBalances")
    preview = {
        "wallet": owner,
        "side": args.side,
        "collateralUsd": str(args.collateral),
        "leverage": str(args.leverage),
        "notionalUsd": str(args.collateral * args.leverage),
        "referencePrice": str(preview_quote.reference),
        "acceptableOpenPrice": str(preview_quote.acceptable),
        "fallbackStopTrigger": str(preview_quote.stop),
        "quote": quote_report(preview_quote),
        "holdSeconds": args.hold_seconds,
        "simulationUnits": simulation.get("unitsConsumed"),
        "startingBalances": {
            key: decimal_text(value) for key, value in starting_balances.items()
        },
        "startupMs": round((time.perf_counter() - startup_started) * 1000, 1),
        "phaseTimingsMs": phase_timings,
        "stopIsAtomic": False,
        "execute": args.execute,
        "submitMode": args.submit_mode,
        "priorityLamports": args.priority_lamports,
        "skipPreflight": args.skip_preflight,
        "maxQuoteAgeAtSubmitSeconds": args.max_quote_age_at_submit,
        "maxQuoteDriftBps": str(args.max_quote_drift_bps),
    }
    print(json.dumps(preview, indent=2))
    if not args.execute:
        if args.json_report:
            args.json_report.parent.mkdir(parents=True, exist_ok=True)
            args.json_report.write_text(
                json.dumps({"preview": preview}, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
        print("Dry run only. Add --execute to enable the local confirmation prompt.")
        return

    if not args.runner_confirmed and not args.i_understand_live_risk:
        typed = input(f'Type "{CONFIRMATION}" to submit the live order: ')
        if typed != CONFIRMATION:
            raise SystemExit("Confirmation did not match; nothing was submitted")

    report: dict[str, Any] = {"preview": preview, "startedAt": time.time()}
    open_order: str | None = None
    stop_order: str | None = None
    execution_error: Exception | None = None
    notional = args.collateral * args.leverage
    wallet_context = (
        temporary_wallet_file(wallet)
        if args.submit_mode == "cli"
        else nullcontext(None)
    )
    with wallet_context as wallet_file:
        try:
            open_quote = fetch_fresh_quote(
                side=args.side,
                acceptable_bps=args.acceptable_bps,
                stop_loss_bps=args.stop_loss_bps,
                max_age_seconds=args.max_price_age,
            )
            report["openQuote"] = quote_report(open_quote)
            open_args = open_arguments(
                args.collateral, args.leverage, args.side, open_quote.acceptable
            )
            if args.submit_mode == "direct-rpc":
                open_result, open_guard = submit_exchange_with_quote_guard(
                    config=config,
                    rpc=rpc,
                    wallet=wallet,
                    arguments=open_args,
                    request_quote=open_quote,
                    refresh_quote=lambda: fetch_fresh_quote(
                        side=args.side,
                        acceptable_bps=args.acceptable_bps,
                        stop_loss_bps=args.stop_loss_bps,
                        max_age_seconds=args.max_price_age,
                    ),
                    max_quote_age_at_submit=args.max_quote_age_at_submit,
                    max_quote_drift_bps=args.max_quote_drift_bps,
                    priority_lamports=args.priority_lamports,
                    skip_preflight=args.skip_preflight,
                )
                report["openRequest"] = direct_report(open_result)
                report["openQuoteGuard"] = open_guard
            else:
                open_result = run_exchange(config, wallet_file, open_args)
                report["openRequest"] = cli_report(open_result)
            open_order = open_result.order
            fill_ms, position = wait_for_position(
                config,
                owner,
                present=True,
                timeout_seconds=45,
                poll_interval_seconds=args.poll_interval,
            )
            report["openRequest"]["positionVisibleMs"] = round(fill_ms, 1)
            report["openRequest"]["endToEndMs"] = round(
                open_result.elapsed_ms + fill_ms, 1
            )
            report["openRequest"]["position"] = position

            stop_quote = fetch_fresh_quote(
                side=args.side,
                acceptable_bps=args.acceptable_bps,
                stop_loss_bps=args.stop_loss_bps,
                max_age_seconds=args.max_price_age,
            )
            stop_args = stop_arguments(args.side, notional, stop_quote.stop)
            report["stopQuote"] = quote_report(stop_quote)
            if args.submit_mode == "direct-rpc":
                stop_result = submit_exchange(
                    config,
                    rpc,
                    wallet,
                    stop_args,
                    priority_lamports=args.priority_lamports,
                    skip_preflight=args.skip_preflight,
                )
                report["stopRequest"] = direct_report(stop_result)
            else:
                stop_result = run_exchange(config, wallet_file, stop_args)
                report["stopRequest"] = cli_report(stop_result)
            stop_order = stop_result.order
            report["stopRequest"]["triggerPrice"] = str(stop_quote.stop)
            time.sleep(args.hold_seconds)
        except Exception as exc:
            execution_error = exc
            report["executionError"] = str(exc)
        finally:
            if not read_actions(config, owner, "positions") and open_order:
                try:
                    pending = read_actions(config, owner, "orders")
                    if pending:
                        if args.submit_mode == "direct-rpc":
                            cancel_open = submit_exchange(
                                config,
                                rpc,
                                wallet,
                                ["close-order", open_order],
                                priority_lamports=args.priority_lamports,
                                skip_preflight=args.skip_preflight,
                            )
                            report["openCancellation"] = direct_report(cancel_open)
                        else:
                            cancel_open = run_exchange(
                                config,
                                wallet_file,
                                ["close-order", open_order],
                            )
                            report["openCancellation"] = cli_report(cancel_open)
                except Exception as exc:
                    report["openCancellation"] = {"error": str(exc)}

            if read_actions(config, owner, "positions"):
                close_errors: list[str] = []
                for attempt in range(1, 4):
                    close_quote = fetch_fresh_close_quote(
                        side=args.side,
                        acceptable_bps=args.acceptable_bps,
                        max_age_seconds=args.max_price_age,
                    )
                    try:
                        close_args = close_arguments(
                            args.side, notional, close_quote.acceptable
                        )
                        if args.submit_mode == "direct-rpc":
                            close_result, close_guard = submit_exchange_with_quote_guard(
                                config=config,
                                rpc=rpc,
                                wallet=wallet,
                                arguments=close_args,
                                request_quote=close_quote,
                                refresh_quote=lambda: fetch_fresh_close_quote(
                                    side=args.side,
                                    acceptable_bps=args.acceptable_bps,
                                    max_age_seconds=args.max_price_age,
                                ),
                                max_quote_age_at_submit=args.max_quote_age_at_submit,
                                max_quote_drift_bps=args.max_quote_drift_bps,
                                priority_lamports=args.priority_lamports,
                                skip_preflight=args.skip_preflight,
                            )
                            close_report = direct_report(close_result)
                            close_report["quoteGuard"] = close_guard
                        else:
                            close_result = run_exchange(
                                config,
                                wallet_file,
                                close_args,
                            )
                            close_report = cli_report(close_result)
                        close_report.update(
                            {
                                "attempt": attempt,
                                "quote": quote_report(close_quote),
                                "acceptablePrice": str(close_quote.acceptable),
                                "priorErrors": close_errors,
                            }
                        )
                        report["closeRequest"] = close_report
                        try:
                            gone_ms, _ = wait_for_position(
                                config,
                                owner,
                                present=False,
                                timeout_seconds=45,
                                poll_interval_seconds=args.poll_interval,
                            )
                            report["closeRequest"]["positionGoneMs"] = round(
                                gone_ms, 1
                            )
                            report["closeRequest"]["endToEndMs"] = round(
                                close_result.elapsed_ms + gone_ms, 1
                            )
                        except TimeoutError as exc:
                            report["closeFailure"] = {
                                "error": str(exc),
                                "requestWasSubmitted": True,
                            }
                        break
                    except Exception as exc:
                        close_errors.append(str(exc))
                        if not read_actions(config, owner, "positions"):
                            report["closeRequest"] = {
                                "positionClosedDuringRetry": True,
                                "errors": close_errors,
                            }
                            break
                        time.sleep(0.5)
                if read_actions(config, owner, "positions"):
                    report["closeFailure"] = {"errors": close_errors}
            else:
                report["closeRequest"] = {"positionAlreadyClosed": True}

            if stop_order:
                try:
                    if args.submit_mode == "direct-rpc":
                        cancel = submit_exchange(
                            config,
                            rpc,
                            wallet,
                            ["close-order", stop_order],
                            priority_lamports=args.priority_lamports,
                            skip_preflight=args.skip_preflight,
                        )
                        report["stopCancellation"] = direct_report(cancel)
                    else:
                        cancel = run_exchange(
                            config,
                            wallet_file,
                            ["close-order", stop_order],
                        )
                        report["stopCancellation"] = cli_report(cancel)
                except Exception as exc:
                    report["stopCancellation"] = {"error": str(exc)}

    report["finishedAt"] = time.time()
    ending_balances = balances(rpc, wallet.pubkey())
    report["endingBalances"] = {
        key: decimal_text(value) for key, value in ending_balances.items()
    }
    report["balanceDelta"] = {
        key: decimal_text(ending_balances[key] - starting_balances[key])
        for key in starting_balances
    }
    report["finalPositions"] = read_actions(config, owner, "positions")
    report["finalOrders"] = read_actions(config, owner, "orders")
    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(
            json.dumps(report, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, indent=2, default=str))
    if report["finalPositions"]:
        raise SystemExit("LIVE POSITION STILL EXISTS: close it in GMTrade immediately")
    if report["finalOrders"]:
        raise SystemExit("PENDING ORDER STILL EXISTS: cancel it in GMTrade immediately")
    if execution_error:
        raise SystemExit(f"Canary failed after cleanup: {execution_error}")


if __name__ == "__main__":
    main()
