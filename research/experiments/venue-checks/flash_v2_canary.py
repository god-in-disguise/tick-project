from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import time
from contextlib import suppress
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests
import websockets
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.transaction import VersionedTransaction


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ENV = Path(__file__).with_name(".env.solana-canary")
DEFAULT_RPC = "https://api.mainnet-beta.solana.com"
USDC_MINT = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
USD_DECIMALS = 6
STATE_HEDGE_AFTER_SECONDS = 0.75
CANARY_MARKETS = (
    "BTC",
    "ETH",
    "SOL",
    "XAU",
    "XAG",
    "EUR",
    "GBP",
    "CRUDEOIL",
    "USDJPY",
    "USDCNH",
)


class FlashTransitionTimeout(RuntimeError):
    def __init__(self, message: str, details: dict[str, Any]) -> None:
        super().__init__(message)
        self.details = details


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT / path


def load_keypair(path: Path) -> Keypair:
    secret = bytes(json.loads(path.read_text()))
    if len(secret) != 64:
        raise ValueError(f"Expected 64 secret bytes in {path}")
    return Keypair.from_bytes(secret)


class SolanaRpc:
    def __init__(self, url: str, session: requests.Session) -> None:
        self.url = url
        self.session = session
        self.request_id = 0

    def call(self, method: str, params: list[Any]) -> Any:
        for attempt in range(5):
            self.request_id += 1
            response = self.session.post(
                self.url,
                json={
                    "jsonrpc": "2.0",
                    "id": self.request_id,
                    "method": method,
                    "params": params,
                },
                timeout=20,
            )
            if response.status_code == 429 and attempt < 4:
                time.sleep(0.5 * (attempt + 1))
                continue
            response.raise_for_status()
            payload = response.json()
            if "error" in payload:
                raise RuntimeError(f"RPC {method} failed: {payload['error']}")
            return payload["result"]
        raise AssertionError("unreachable")

    def sol_balance(self, owner: Pubkey) -> Decimal:
        result = self.call("getBalance", [str(owner), {"commitment": "confirmed"}])
        return Decimal(result["value"]).scaleb(-9)

    def token_balance(self, owner: Pubkey, mint: Pubkey) -> Decimal:
        result = self.call(
            "getTokenAccountsByOwner",
            [
                str(owner),
                {"mint": str(mint)},
                {"encoding": "jsonParsed", "commitment": "confirmed"},
            ],
        )
        total = Decimal(0)
        for row in result["value"]:
            amount = row["account"]["data"]["parsed"]["info"]["tokenAmount"]
            total += Decimal(amount["amount"]).scaleb(-int(amount["decimals"]))
        return total

    def signature_status(self, signature: str) -> dict[str, Any] | None:
        result = self.call(
            "getSignatureStatuses",
            [[signature], {"searchTransactionHistory": True}],
        )
        return result["value"][0]

    def wait_for_signature(
        self, signature: str, timeout_seconds: float = 45
    ) -> tuple[float, dict[str, Any]]:
        started = time.perf_counter()
        last: dict[str, Any] | None = None
        while time.perf_counter() - started < timeout_seconds:
            last = self.signature_status(signature)
            if last:
                if last.get("err") is not None:
                    raise RuntimeError(f"Transaction {signature} failed: {last['err']}")
                if last.get("confirmationStatus") in {"confirmed", "finalized"}:
                    return (time.perf_counter() - started) * 1000, last
            time.sleep(0.2)
        raise TimeoutError(f"Transaction {signature} not confirmed; last={last}")


class FlashApi:
    def __init__(self, url: str, session: requests.Session) -> None:
        self.url = url.rstrip("/")
        self.session = session

    def get(self, path: str) -> Any:
        response = self.session.get(f"{self.url}{path}", timeout=20)
        response.raise_for_status()
        return response.json()

    def post(
        self,
        path: str,
        body: dict[str, Any],
        timeout_seconds: float = 30,
    ) -> tuple[float, Any]:
        started = time.perf_counter()
        response = self.session.post(
            f"{self.url}{path}", json=body, timeout=timeout_seconds
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        if not response.ok:
            raise RuntimeError(
                f"Flash {path} failed ({response.status_code}): {response.text}"
            )
        return elapsed_ms, response.json()

    def owner(self, owner: Pubkey) -> dict[str, Any]:
        return self.get(f"/owner/{owner}")


def sign_transaction(
    transaction_base64: str, signer: Keypair | list[Keypair]
) -> tuple[str, str]:
    unsigned = VersionedTransaction.from_bytes(base64.b64decode(transaction_base64))
    signer_count = unsigned.message.header.num_required_signatures
    required = list(unsigned.message.account_keys[:signer_count])
    signers = signer if isinstance(signer, list) else [signer]
    signers_by_pubkey = {item.pubkey(): item for item in signers}
    if set(required) != set(signers_by_pubkey):
        raise RuntimeError(
            "Unexpected required signers: "
            + ", ".join(map(str, required))
            + "; provided: "
            + ", ".join(map(str, signers_by_pubkey))
        )
    signed = VersionedTransaction(
        unsigned.message, [signers_by_pubkey[pubkey] for pubkey in required]
    )
    signature = str(signed.signatures[0])
    return base64.b64encode(bytes(signed)).decode("ascii"), signature


def compact(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key == "transactionBase64":
                continue
            if key == "basketData" and isinstance(item, str):
                result["basketDataBase64Bytes"] = len(item)
                continue
            result[key] = compact(item)
        return result
    if isinstance(value, list):
        return [compact(item) for item in value]
    return value


def write_report(path: Path, timeline: dict[str, Any]) -> None:
    path.write_text(json.dumps(timeline, indent=2, sort_keys=True) + "\n")


def raw_position_size_usd_ui(raw_basket: dict[str, Any]) -> str:
    positions = raw_basket.get("account", {}).get("positions") or []
    if len(positions) != 1:
        raise RuntimeError(
            "Expected exactly one authoritative Flash position; "
            f"got {len(positions)}"
        )
    size_usd = positions[0].get("position", {}).get("sizeUsd")
    if size_usd is None:
        raise RuntimeError(f"Raw Flash position has no sizeUsd: {compact(positions[0])}")
    return format(Decimal(str(size_usd)).scaleb(-USD_DECIMALS), "f")


def submit_built_transaction(
    *,
    api: FlashApi,
    rpc: SolanaRpc,
    signer: Keypair | list[Keypair],
    builder_path: str,
    builder_body: dict[str, Any],
    wait_for_base_confirmation: bool,
    skip_preflight: bool = False,
) -> dict[str, Any]:
    build_ms, built = api.post(builder_path, builder_body)
    transaction_base64 = built.get("transactionBase64")
    if not transaction_base64:
        raise RuntimeError(f"No transactionBase64 returned: {built}")

    sign_started = time.perf_counter()
    signed_base64, local_signature = sign_transaction(transaction_base64, signer)
    sign_ms = (time.perf_counter() - sign_started) * 1000

    submit_ms, submitted = api.post(
        "/transaction-builder/submit-transaction",
        {
            "transactionBase64": signed_base64,
            "skipPreflight": skip_preflight,
        },
    )
    remote_signature = submitted.get("signature") or submitted.get("txSignature")
    if remote_signature and remote_signature != local_signature:
        raise RuntimeError(
            f"Signature mismatch: local={local_signature} remote={remote_signature}"
        )

    result: dict[str, Any] = {
        "builderPath": builder_path,
        "builderMs": round(build_ms, 3),
        "signMs": round(sign_ms, 3),
        "submitMs": round(submit_ms, 3),
        "skipPreflight": skip_preflight,
        "signature": local_signature,
        "builder": compact(built),
        "submit": compact(submitted),
    }
    if wait_for_base_confirmation:
        confirmation_ms, status = rpc.wait_for_signature(local_signature)
        result["confirmationMs"] = round(confirmation_ms, 3)
        result["status"] = status
    return result


def wait_for_owner(
    api: FlashApi,
    owner: Pubkey,
    predicate: Any,
    timeout_seconds: float = 30,
) -> tuple[float, dict[str, Any]]:
    started = time.perf_counter()
    last: dict[str, Any] = {}
    while time.perf_counter() - started < timeout_seconds:
        last = api.owner(owner)
        if predicate(last):
            return (time.perf_counter() - started) * 1000, last
        time.sleep(0.25)
    raise TimeoutError(f"Owner state did not converge; last={compact(last)}")


def wait_for_raw_basket(
    api: FlashApi,
    basket_pubkey: str,
    predicate: Any,
    timeout_seconds: float = 30,
) -> tuple[float, dict[str, Any]]:
    started = time.perf_counter()
    last: dict[str, Any] = {}
    while time.perf_counter() - started < timeout_seconds:
        last = api.get(f"/raw/baskets/{basket_pubkey}")
        if predicate(last):
            return (time.perf_counter() - started) * 1000, last
        time.sleep(0.1)
    raise TimeoutError(f"Raw basket state did not converge; last={compact(last)}")


def ws_position_metrics(message: dict[str, Any]) -> dict[str, Any] | None:
    message_type = message.get("type")
    data = message.get("data")
    if not isinstance(data, dict):
        return None
    if message_type == "metrics":
        return data
    if message_type == "basket":
        metrics = data.get("positionMetrics")
        return metrics if isinstance(metrics, dict) else None
    return None


async def receive_until(
    websocket: Any,
    predicate: Any,
    *,
    timeout_seconds: float,
) -> tuple[float, dict[str, Any], int]:
    started = time.perf_counter()
    message_count = 0
    while time.perf_counter() - started < timeout_seconds:
        remaining = timeout_seconds - (time.perf_counter() - started)
        raw = await asyncio.wait_for(websocket.recv(), timeout=remaining)
        if not isinstance(raw, str):
            continue
        message = json.loads(raw)
        message_count += 1
        if predicate(message):
            return (time.perf_counter() - started) * 1000, message, message_count
    raise TimeoutError("Flash owner WebSocket transition timed out")


def prepare_transaction(
    api: FlashApi,
    signer: Keypair,
    builder_path: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    build_ms, built = api.post(builder_path, body)
    transaction_base64 = built.get("transactionBase64")
    if not transaction_base64:
        raise RuntimeError(f"No transactionBase64 returned: {built}")
    sign_started = time.perf_counter()
    signed_base64, signature = sign_transaction(transaction_base64, signer)
    sign_ms = (time.perf_counter() - sign_started) * 1000
    return {
        "buildMs": round(build_ms, 3),
        "signMs": round(sign_ms, 3),
        "signature": signature,
        "transactionBase64": signed_base64,
        "quote": compact(built),
    }


async def submit_prepared(
    api: FlashApi,
    prepared: dict[str, Any],
    *,
    skip_preflight: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()
    attempts: list[dict[str, Any]] = []
    submitted = None
    error = None
    for attempt in range(2):
        attempt_started = time.perf_counter()
        try:
            _, submitted = await asyncio.to_thread(
                api.post,
                "/transaction-builder/submit-transaction",
                {
                    "transactionBase64": prepared["transactionBase64"],
                    "skipPreflight": skip_preflight,
                },
                3,
            )
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "ms": round((time.perf_counter() - attempt_started) * 1000, 3),
                    "response": compact(submitted),
                    "error": None,
                }
            )
            error = None
            break
        except Exception as exc:  # Retry the exact same signed transaction.
            error = f"{type(exc).__name__}: {exc}"
            lowered = error.lower()
            already_processed = "already processed" in lowered
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "ms": round((time.perf_counter() - attempt_started) * 1000, 3),
                    "response": {"alreadyProcessed": True} if already_processed else None,
                    "error": None if already_processed else error,
                }
            )
            if already_processed:
                submitted = {"alreadyProcessed": True}
                error = None
                break
            if any(
                marker in lowered
                for marker in (
                    "custom program error",
                    "instructionerror",
                    "invalid transaction",
                    "signature verification failed",
                    "transaction simulation failed",
                )
            ):
                break
    return {
        "submitMs": round((time.perf_counter() - started) * 1000, 3),
        "response": compact(submitted),
        "error": error,
        "attempts": attempts,
    }


async def submit_and_observe(
    *,
    api: FlashApi,
    owner: Pubkey,
    websocket: Any,
    prepared: dict[str, Any],
    message_predicate: Any,
    basket_pubkey: str,
    raw_snapshot_predicate: Any,
    timeout_seconds: float,
    drop_primary: bool = False,
    skip_preflight: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()
    event_task = asyncio.create_task(
        receive_until(
            websocket,
            message_predicate,
            timeout_seconds=timeout_seconds,
        )
    )
    submission = (
        {
            "submitMs": 0,
            "response": None,
            "error": "intentionally_dropped_before_transport",
            "attempts": [],
        }
        if drop_primary
        else await submit_prepared(api, prepared, skip_preflight=skip_preflight)
    )
    raw_started = time.perf_counter()
    raw_snapshot: dict[str, Any] = {}
    hedge_submission = None
    while time.perf_counter() - raw_started < timeout_seconds:
        raw_snapshot = await asyncio.to_thread(
            api.get, f"/raw/baskets/{basket_pubkey}"
        )
        if raw_snapshot_predicate(raw_snapshot):
            break
        if (
            hedge_submission is None
            and time.perf_counter() - raw_started >= STATE_HEDGE_AFTER_SECONDS
        ):
            hedge_submission = await submit_prepared(
                api,
                prepared,
                skip_preflight=skip_preflight,
            )
        await asyncio.sleep(0.1)
    else:
        snapshot = await asyncio.to_thread(api.owner, owner)
        event_task.cancel()
        with suppress(asyncio.CancelledError, TimeoutError):
            await event_task
        details = {
            "submission": submission,
            "stateHedgeSubmission": hedge_submission,
            "requestToVisibleMs": None,
            "rawBasketWaitMs": round(
                (time.perf_counter() - raw_started) * 1000, 3
            ),
            "authoritativeRawBasket": compact(raw_snapshot),
            "detectionSource": "raw_basket_timeout",
        }
        raise FlashTransitionTimeout(
            "Flash raw basket did not reach the authoritative state; "
            f"owner={compact(snapshot)} submission={submission} "
            f"hedge={hedge_submission}",
            details,
        )

    raw_wait_ms = (time.perf_counter() - raw_started) * 1000

    event_wait_ms = None
    message_count = None
    message = None
    if event_task.done():
        with suppress(TimeoutError):
            event_wait_ms, message, message_count = await event_task
    else:
        event_task.cancel()
        with suppress(asyncio.CancelledError, TimeoutError):
            await event_task

    visible_ms = (time.perf_counter() - started) * 1000
    return {
        "submission": submission,
        "stateHedgeSubmission": hedge_submission,
        "requestToVisibleMs": round(visible_ms, 3),
        "rawBasketWaitMs": round(raw_wait_ms, 3),
        "eventWaitMs": round(event_wait_ms, 3) if event_wait_ms is not None else None,
        "wsMessages": message_count,
        "event": compact(message),
        "authoritativeRawBasket": compact(raw_snapshot),
        "detectionSource": "raw_basket",
    }


async def cycle(
    args: argparse.Namespace,
    context: tuple[Keypair, FlashApi, SolanaRpc] | None = None,
) -> dict[str, Any]:
    signer, api, rpc = context or build_context(args)
    owner = signer.pubkey()
    initial = status_from_context(signer, api, rpc)
    basket_pubkey = initial["flashOwner"].get("basketPubkey")
    if not basket_pubkey:
        raise RuntimeError("Flash basket is not initialized")
    initial_raw_basket = await asyncio.to_thread(
        api.get, f"/raw/baskets/{basket_pubkey}"
    )
    raw_account = initial_raw_basket.get("account", {})
    if raw_account.get("positions") or raw_account.get("orders"):
        raise RuntimeError(
            "Flash raw basket is not empty; refusing to open: "
            f"{compact(initial_raw_basket)}"
        )

    open_body = {
        "inputTokenSymbol": "USDC",
        "outputTokenSymbol": args.market,
        "inputAmountUi": args.amount,
        "leverage": args.leverage,
        "tradeType": args.side,
        "orderType": "MARKET",
        "owner": str(owner),
        "slippagePercentage": args.slippage,
    }
    prepared_open = await asyncio.to_thread(
        prepare_transaction,
        api,
        signer,
        "/transaction-builder/open-position",
        open_body,
    )

    ws_url = (
        api.url.replace("https://", "wss://").replace("http://", "ws://")
        + f"/owner/{owner}/ws?updateIntervalMs=100"
    )
    timeline: dict[str, Any] = {
        "startedAt": utc_now(),
        "owner": str(owner),
        "market": args.market,
        "side": args.side,
        "amountUsdc": args.amount,
        "leverage": args.leverage,
        "initial": initial,
        "initialRawBasket": compact(initial_raw_basket),
        "open": compact(prepared_open),
    }
    report_path = (
        Path(__file__).with_name("reports")
        / "flash"
        / f"cycle-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    timeline["reportPath"] = str(report_path.relative_to(ROOT))
    write_report(report_path, timeline)
    try:
        async with websockets.connect(
            ws_url,
            open_timeout=15,
            ping_interval=20,
            ping_timeout=10,
            max_size=2**20,
        ) as websocket:
            initial_raw = await asyncio.wait_for(websocket.recv(), timeout=15)
            initial_message = json.loads(initial_raw)
            timeline["wsInitial"] = compact(initial_message)
            write_report(report_path, timeline)

            try:
                open_observation = await submit_and_observe(
                    api=api,
                    owner=owner,
                    websocket=websocket,
                    prepared=prepared_open,
                    message_predicate=lambda message: message.get("type") == "basket"
                    and bool(ws_position_metrics(message)),
                    basket_pubkey=basket_pubkey,
                    raw_snapshot_predicate=lambda snapshot: len(
                        snapshot.get("account", {}).get("positions") or []
                    )
                    == 1,
                    timeout_seconds=args.timeout,
                    drop_primary=args.force_hedge == "open",
                    skip_preflight=not args.use_preflight,
                )
            except FlashTransitionTimeout as exc:
                timeline["open"].update(exc.details)
                write_report(report_path, timeline)
                raise
            timeline["open"].update(open_observation)
            write_report(report_path, timeline)

            close_size = raw_position_size_usd_ui(
                timeline["open"]["authoritativeRawBasket"]
            )
            close_body = {
                "marketSymbol": args.market,
                "side": args.side,
                "inputUsdUi": str(close_size),
                "withdrawTokenSymbol": "USDC",
                "owner": str(owner),
                "closeAll": True,
                "slippagePercentage": args.slippage,
            }
            prepared_close = await asyncio.to_thread(
                prepare_transaction,
                api,
                signer,
                "/transaction-builder/close-position",
                close_body,
            )
            timeline["close"] = compact(prepared_close)
            write_report(report_path, timeline)

            try:
                close_observation = await submit_and_observe(
                    api=api,
                    owner=owner,
                    websocket=websocket,
                    prepared=prepared_close,
                    message_predicate=lambda message: message.get("type") == "basket"
                    and ws_position_metrics(message) == {},
                    basket_pubkey=basket_pubkey,
                    raw_snapshot_predicate=lambda snapshot: not snapshot.get(
                        "account", {}
                    ).get("positions"),
                    timeout_seconds=args.timeout,
                    drop_primary=args.force_hedge == "close",
                    skip_preflight=not args.use_preflight,
                )
            except FlashTransitionTimeout as exc:
                timeline["close"].update(exc.details)
                write_report(report_path, timeline)
                raise
            timeline["close"].update(close_observation)
            write_report(report_path, timeline)

        final_raw_basket = await asyncio.to_thread(
            api.get, f"/raw/baskets/{basket_pubkey}"
        )
        if final_raw_basket.get("account", {}).get("positions"):
            raise RuntimeError(
                "Flash raw basket still has a position after close: "
                f"{compact(final_raw_basket)}"
            )
        timeline["finishedAt"] = utc_now()
        timeline["finalRawBasket"] = compact(final_raw_basket)
        timeline["final"] = await asyncio.to_thread(
            status_from_context, signer, api, rpc
        )
    except Exception as exc:
        timeline["failedAt"] = utc_now()
        timeline["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        write_report(report_path, timeline)
    return timeline


async def batch(args: argparse.Namespace) -> dict[str, Any]:
    context = build_context(args)
    markets = [item.strip().upper() for item in args.markets.split(",") if item]
    if not markets or any(item not in CANARY_MARKETS for item in markets):
        raise ValueError(f"markets must contain only {', '.join(CANARY_MARKETS)}")

    rows: list[dict[str, Any]] = []
    failure: dict[str, Any] | None = None
    for index in range(args.count):
        cycle_args = argparse.Namespace(**vars(args))
        cycle_args.market = markets[index % len(markets)]
        cycle_args.side = "LONG" if index % 2 == 0 else "SHORT"
        try:
            result = await cycle(cycle_args, context=context)
        except Exception as exc:
            recovery = None
            recovery_error = None
            current = await asyncio.to_thread(status_from_context, *context)
            basket_pubkey = current["flashOwner"].get("basketPubkey")
            raw_current = (
                await asyncio.to_thread(
                    context[1].get, f"/raw/baskets/{basket_pubkey}"
                )
                if basket_pubkey
                else {}
            )
            if raw_current.get("account", {}).get("positions"):
                try:
                    recovery = await asyncio.to_thread(close_existing, cycle_args)
                except Exception as recovery_exc:
                    recovery_error = (
                        f"{type(recovery_exc).__name__}: {recovery_exc}"
                    )
            failure = {
                "index": index + 1,
                "market": cycle_args.market,
                "side": cycle_args.side,
                "error": f"{type(exc).__name__}: {exc}",
                "stateAtFailure": current,
                "rawStateAtFailure": compact(raw_current),
                "recovery": recovery,
                "recoveryError": recovery_error,
            }
            break
        open_result = result["open"]
        close_result = result["close"]
        rows.append(
            {
                "index": index + 1,
                "market": cycle_args.market,
                "side": cycle_args.side,
                "reportPath": result["reportPath"],
                "openBuildMs": open_result["buildMs"],
                "openSubmitToVisibleMs": open_result["requestToVisibleMs"],
                "openFullMs": round(
                    open_result["buildMs"]
                    + open_result["signMs"]
                    + open_result["requestToVisibleMs"],
                    3,
                ),
                "closeBuildMs": close_result["buildMs"],
                "closeSubmitToVisibleMs": close_result["requestToVisibleMs"],
                "closeFullMs": round(
                    close_result["buildMs"]
                    + close_result["signMs"]
                    + close_result["requestToVisibleMs"],
                    3,
                ),
            }
        )
        if index + 1 < args.count:
            await asyncio.sleep(args.interval)

    return {
        "at": utc_now(),
        "count": len(rows),
        "amountUsdc": args.amount,
        "leverage": args.leverage,
        "rows": rows,
        "failure": failure,
        "final": status_from_context(*context),
    }


def build_context(args: argparse.Namespace) -> tuple[Keypair, FlashApi, SolanaRpc]:
    env = load_env(Path(args.env))
    keypair_path = resolve_path(
        os.getenv("SOLANA_CANARY_KEYPAIR_PATH")
        or env["SOLANA_CANARY_KEYPAIR_PATH"]
    )
    signer = load_keypair(keypair_path)
    expected = os.getenv("SOLANA_CANARY_PUBLIC_KEY") or env.get(
        "SOLANA_CANARY_PUBLIC_KEY"
    )
    if expected and str(signer.pubkey()) != expected:
        raise RuntimeError(
            f"Canary signer mismatch: expected={expected} got={signer.pubkey()}"
        )

    session = requests.Session()
    session.headers.update({"user-agent": "tick-flash-canary/0.1"})
    api_url = os.getenv("FLASH_API_URL") or env.get(
        "FLASH_API_URL", "https://flashapi.trade"
    )
    rpc_url = os.getenv("SOLANA_RPC_URL") or env.get("SOLANA_RPC_URL", DEFAULT_RPC)
    return signer, FlashApi(api_url, session), SolanaRpc(rpc_url, session)


def status_from_context(
    signer: Keypair, api: FlashApi, rpc: SolanaRpc
) -> dict[str, Any]:
    owner = signer.pubkey()
    return {
        "at": utc_now(),
        "owner": str(owner),
        "sol": str(rpc.sol_balance(owner)),
        "walletUsdc": str(rpc.token_balance(owner, USDC_MINT)),
        "flashOwner": compact(api.owner(owner)),
    }


def status(args: argparse.Namespace) -> dict[str, Any]:
    return status_from_context(*build_context(args))


def quote(args: argparse.Namespace) -> dict[str, Any]:
    signer, api, _ = build_context(args)
    body: dict[str, Any] = {
        "inputTokenSymbol": "USDC",
        "outputTokenSymbol": args.market,
        "inputAmountUi": args.amount,
        "leverage": args.leverage,
        "tradeType": args.side,
        "orderType": "MARKET",
        "slippagePercentage": args.slippage,
    }
    if args.with_owner:
        body["owner"] = str(signer.pubkey())
    elapsed_ms, response = api.post("/transaction-builder/open-position", body)
    return {"at": utc_now(), "requestMs": round(elapsed_ms, 3), **compact(response)}


def setup(args: argparse.Namespace) -> dict[str, Any]:
    signer, api, rpc = build_context(args)
    owner = signer.pubkey()
    before = status_from_context(signer, api, rpc)
    if before["flashOwner"].get("basketPubkey"):
        raise RuntimeError("Flash basket already exists; refusing to repeat setup")

    actions: list[dict[str, Any]] = []
    actions.append(
        submit_built_transaction(
            api=api,
            rpc=rpc,
            signer=signer,
            builder_path="/transaction-builder/init-basket",
            builder_body={"owner": str(owner)},
            wait_for_base_confirmation=True,
        )
    )
    index_ms, owner_after_init = wait_for_owner(
        api, owner, lambda state: bool(state.get("basketPubkey"))
    )

    actions.append(
        submit_built_transaction(
            api=api,
            rpc=rpc,
            signer=signer,
            builder_path="/transaction-builder/init-deposit-ledger",
            builder_body={"owner": str(owner)},
            wait_for_base_confirmation=True,
        )
    )
    # Flash's submission RPC can lag the confirmation RPC briefly. Let its
    # simulator observe the newly created ledger before building the deposit.
    time.sleep(2)
    actions.append(
        submit_built_transaction(
            api=api,
            rpc=rpc,
            signer=signer,
            builder_path="/transaction-builder/deposit-direct",
            builder_body={
                "owner": str(owner),
                "tokenMint": str(USDC_MINT),
                "amount": args.deposit,
            },
            wait_for_base_confirmation=True,
        )
    )
    actions.append(
        submit_built_transaction(
            api=api,
            rpc=rpc,
            signer=signer,
            builder_path="/transaction-builder/delegate-basket",
            builder_body={"owner": str(owner)},
            wait_for_base_confirmation=True,
            skip_preflight=True,
        )
    )
    return {
        "at": utc_now(),
        "owner": str(owner),
        "depositUsdc": args.deposit,
        "basketIndexMs": round(index_ms, 3),
        "ownerAfterInit": compact(owner_after_init),
        "actions": actions,
        "after": status_from_context(signer, api, rpc),
    }


def deposit(args: argparse.Namespace) -> dict[str, Any]:
    signer, api, rpc = build_context(args)
    owner = signer.pubkey()
    before = status_from_context(signer, api, rpc)
    if not before["flashOwner"].get("basketPubkey"):
        raise RuntimeError("Flash basket is not initialized")
    if Decimal(before["walletUsdc"]) < Decimal(args.amount):
        raise RuntimeError(
            f"Insufficient wallet USDC: {before['walletUsdc']} < {args.amount}"
        )
    action = submit_built_transaction(
        api=api,
        rpc=rpc,
        signer=signer,
        builder_path="/transaction-builder/deposit-direct",
        builder_body={
            "owner": str(owner),
            "tokenMint": str(USDC_MINT),
            "amount": args.amount,
        },
        wait_for_base_confirmation=True,
        skip_preflight=args.skip_preflight,
    )
    return {
        "at": utc_now(),
        "owner": str(owner),
        "amountUsdc": args.amount,
        "before": before,
        "action": action,
        "after": status_from_context(signer, api, rpc),
    }


def delegate(args: argparse.Namespace) -> dict[str, Any]:
    signer, api, rpc = build_context(args)
    owner = signer.pubkey()
    before = status_from_context(signer, api, rpc)
    if not before["flashOwner"].get("basketPubkey"):
        raise RuntimeError("Flash basket is not initialized")
    action = submit_built_transaction(
        api=api,
        rpc=rpc,
        signer=signer,
        builder_path="/transaction-builder/delegate-basket",
        builder_body={"owner": str(owner)},
        wait_for_base_confirmation=True,
        skip_preflight=True,
    )
    return {
        "at": utc_now(),
        "owner": str(owner),
        "before": before,
        "action": action,
        "after": status_from_context(signer, api, rpc),
    }


def close_existing(args: argparse.Namespace) -> dict[str, Any]:
    signer, api, rpc = build_context(args)
    owner = signer.pubkey()
    before = status_from_context(signer, api, rpc)
    basket_pubkey = before["flashOwner"].get("basketPubkey")
    if not basket_pubkey:
        raise RuntimeError("Flash basket is not initialized")
    raw_before = api.get(f"/raw/baskets/{basket_pubkey}")
    raw_positions = raw_before.get("account", {}).get("positions") or []
    positions = before["flashOwner"].get("positionMetrics") or {}
    if raw_positions and len(positions) < len(raw_positions):
        _, refreshed = wait_for_owner(
            api,
            owner,
            lambda state: len(state.get("positionMetrics") or {})
            >= len(raw_positions),
            timeout_seconds=min(args.timeout, 10),
        )
        positions = refreshed.get("positionMetrics") or {}
    if not raw_positions and not positions:
        raise RuntimeError("No Flash positions to close")
    if len(positions) < len(raw_positions):
        raise RuntimeError(
            "Raw Flash positions are not yet decodable through owner state: "
            f"raw={compact(raw_before)} owner={compact(before)}"
        )
    started = time.perf_counter()
    actions: list[dict[str, Any]] = []
    for position_key, position in positions.items():
        raw_position = next(
            (
                item
                for item in raw_positions
                if item.get("market") == position_key
            ),
            None,
        )
        raw_size_usd = (
            raw_position.get("position", {}).get("sizeUsd")
            if raw_position
            else None
        )
        close_size = (
            format(Decimal(str(raw_size_usd)).scaleb(-USD_DECIMALS), "f")
            if raw_size_usd is not None
            else position["sizeUsdUi"]
        )
        prepared = prepare_transaction(
            api,
            signer,
            "/transaction-builder/close-position",
            {
                "marketSymbol": position["marketSymbol"],
                "side": position["sideUi"].upper(),
                "inputUsdUi": close_size,
                "withdrawTokenSymbol": "USDC",
                "owner": str(owner),
                "closeAll": True,
                "slippagePercentage": args.slippage,
            },
        )
        submission = asyncio.run(submit_prepared(api, prepared))
        actions.append(
            {
                "positionKey": position_key,
                "market": position["marketSymbol"],
                **compact(prepared),
                "submission": submission,
            }
        )

    raw_basket: dict[str, Any] = {}
    raw_wait_started = time.perf_counter()
    while time.perf_counter() - raw_wait_started < args.timeout:
        raw_basket = api.get(f"/raw/baskets/{basket_pubkey}")
        if not raw_basket.get("account", {}).get("positions"):
            break
        time.sleep(0.25)
    else:
        raise TimeoutError(f"Raw Flash basket still has positions: {raw_basket}")

    owner_after_close = api.owner(owner)
    return {
        "at": utc_now(),
        "owner": str(owner),
        "before": before,
        "closes": actions,
        "requestToRawBasketEmptyMs": round(
            (time.perf_counter() - started) * 1000, 3
        ),
        "rawBasket": compact(raw_basket),
        "ownerAfterClose": compact(owner_after_close),
        "after": status_from_context(signer, api, rpc),
    }


def load_or_create_fee_payer(path: Path) -> Keypair:
    if path.exists():
        return load_keypair(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    signer = Keypair()
    path.write_text(json.dumps(list(bytes(signer))) + "\n")
    path.chmod(0o600)
    return signer


def withdraw(args: argparse.Namespace) -> dict[str, Any]:
    signer, api, rpc = build_context(args)
    owner = signer.pubkey()
    before = status_from_context(signer, api, rpc)
    if before["flashOwner"].get("positionMetrics"):
        raise RuntimeError("Refusing to withdraw with an open Flash position")

    fee_payer_path = resolve_path(args.fee_payer_keypair)
    fee_payer = load_or_create_fee_payer(fee_payer_path)
    fee_payer_balance_lamports = int(rpc.sol_balance(fee_payer.pubkey()).scaleb(9))
    target_lamports = args.fee_payer_target_lamports
    fee_payer_top_up_lamports = max(0, target_lamports - fee_payer_balance_lamports)
    build_ms, built = api.post(
        "/transaction-builder/withdraw",
        {
            "owner": str(owner),
            "tokenSymbol": "USDC",
            "amount": args.amount,
            "feePayer": str(fee_payer.pubkey()),
            "feePayerTopUpLamports": fee_payer_top_up_lamports,
        },
    )
    if built.get("custodySettlementRequired"):
        raise RuntimeError(
            "Flash requires a custody settlement before withdrawal; "
            "refusing to continue automatically"
        )
    transaction_base64 = built.get("transactionBase64")
    if not transaction_base64:
        raise RuntimeError(f"No transactionBase64 returned: {built}")

    sign_started = time.perf_counter()
    signed_base64, local_signature = sign_transaction(
        transaction_base64, [signer, fee_payer]
    )
    sign_ms = (time.perf_counter() - sign_started) * 1000
    submit_ms, submitted = api.post(
        "/transaction-builder/submit-transaction",
        {
            "transactionBase64": signed_base64,
            "skipPreflight": args.skip_preflight,
        },
    )
    remote_signature = submitted.get("signature") or submitted.get("txSignature")
    if remote_signature and remote_signature != local_signature:
        raise RuntimeError(
            f"Signature mismatch: local={local_signature} remote={remote_signature}"
        )
    confirmation_ms, confirmation = rpc.wait_for_signature(local_signature)

    wallet_before = Decimal(before["walletUsdc"])
    settle_started = time.perf_counter()
    wallet_after = wallet_before
    while time.perf_counter() - settle_started < args.timeout:
        wallet_after = rpc.token_balance(owner, USDC_MINT)
        if wallet_after > wallet_before:
            break
        time.sleep(0.25)

    return {
        "at": utc_now(),
        "owner": str(owner),
        "feePayer": str(fee_payer.pubkey()),
        "feePayerBalanceLamportsBefore": fee_payer_balance_lamports,
        "feePayerTopUpLamports": fee_payer_top_up_lamports,
        "amountUsdc": args.amount,
        "before": before,
        "action": {
            "builderMs": round(build_ms, 3),
            "signMs": round(sign_ms, 3),
            "submitMs": round(submit_ms, 3),
            "skipPreflight": args.skip_preflight,
            "confirmationMs": round(confirmation_ms, 3),
            "signature": local_signature,
            "builder": compact(built),
            "submit": compact(submitted),
            "status": confirmation,
        },
        "walletSettlementMs": round((time.perf_counter() - settle_started) * 1000, 3),
        "walletUsdcBefore": str(wallet_before),
        "walletUsdcAfter": str(wallet_after),
        "after": status_from_context(signer, api, rpc),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Flash Trade V2 funded canary")
    parser.add_argument("--env", default=str(DEFAULT_ENV))
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status")

    quote_parser = subparsers.add_parser("quote")
    quote_parser.add_argument("--market", choices=CANARY_MARKETS, default="BTC")
    quote_parser.add_argument("--amount", default="10")
    quote_parser.add_argument("--leverage", type=float, default=500)
    quote_parser.add_argument("--side", choices=["LONG", "SHORT"], default="LONG")
    quote_parser.add_argument("--slippage", default="0.5")
    quote_parser.add_argument("--with-owner", action="store_true")

    setup_parser = subparsers.add_parser("setup")
    setup_parser.add_argument("--deposit", default="15")
    setup_parser.add_argument("--execute", action="store_true")

    deposit_parser = subparsers.add_parser("deposit")
    deposit_parser.add_argument("--amount", default="15")
    deposit_parser.add_argument("--skip-preflight", action="store_true")
    deposit_parser.add_argument("--execute", action="store_true")

    delegate_parser = subparsers.add_parser("delegate")
    delegate_parser.add_argument("--execute", action="store_true")

    close_parser = subparsers.add_parser("close")
    close_parser.add_argument("--slippage", default="0.5")
    close_parser.add_argument("--timeout", type=float, default=30)
    close_parser.add_argument("--execute", action="store_true")

    withdraw_parser = subparsers.add_parser("withdraw")
    withdraw_parser.add_argument("--amount", default="13.33")
    withdraw_parser.add_argument(
        "--fee-payer-keypair",
        default="research/experiments/venue-checks/.local/flash-withdraw-fee-payer.json",
    )
    withdraw_parser.add_argument(
        "--fee-payer-target-lamports", type=int, default=11_000_000
    )
    withdraw_parser.add_argument("--timeout", type=float, default=45)
    withdraw_parser.add_argument("--skip-preflight", action="store_true")
    withdraw_parser.add_argument("--execute", action="store_true")

    cycle_parser = subparsers.add_parser("cycle")
    cycle_parser.add_argument("--market", choices=CANARY_MARKETS, default="BTC")
    cycle_parser.add_argument("--amount", default="10")
    cycle_parser.add_argument("--leverage", type=float, default=500)
    cycle_parser.add_argument("--side", choices=["LONG", "SHORT"], default="LONG")
    cycle_parser.add_argument("--slippage", default="0.5")
    cycle_parser.add_argument("--timeout", type=float, default=20)
    cycle_parser.add_argument(
        "--force-hedge",
        choices=["none", "open", "close"],
        default="none",
        help="Drop the selected primary submission and send its identical signed hedge.",
    )
    cycle_parser.add_argument(
        "--use-preflight",
        action="store_true",
        help="Ask Flash to simulate before routing the signed transaction.",
    )
    cycle_parser.add_argument("--execute", action="store_true")

    batch_parser = subparsers.add_parser("batch")
    batch_parser.add_argument("--count", type=int, default=20)
    batch_parser.add_argument("--markets", default="BTC,ETH")
    batch_parser.add_argument("--amount", default="10")
    batch_parser.add_argument("--leverage", type=float, default=500)
    batch_parser.add_argument("--slippage", default="0.5")
    batch_parser.add_argument("--timeout", type=float, default=20)
    batch_parser.add_argument("--interval", type=float, default=0.5)
    batch_parser.add_argument("--force-hedge", choices=["none"], default="none")
    batch_parser.add_argument("--use-preflight", action="store_true")
    batch_parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "status":
        result = status(args)
    elif args.command == "quote":
        result = quote(args)
    elif args.command == "setup":
        if not args.execute:
            raise SystemExit("setup requires --execute")
        result = setup(args)
    elif args.command == "deposit":
        if not args.execute:
            raise SystemExit("deposit requires --execute")
        result = deposit(args)
    elif args.command == "delegate":
        if not args.execute:
            raise SystemExit("delegate requires --execute")
        result = delegate(args)
    elif args.command == "close":
        if not args.execute:
            raise SystemExit("close requires --execute")
        result = close_existing(args)
    elif args.command == "withdraw":
        if not args.execute:
            raise SystemExit("withdraw requires --execute")
        result = withdraw(args)
    elif args.command == "cycle":
        if not args.execute:
            raise SystemExit("cycle requires --execute")
        result = asyncio.run(cycle(args))
    elif args.command == "batch":
        if not args.execute:
            raise SystemExit("batch requires --execute")
        result = asyncio.run(batch(args))
    else:
        raise AssertionError(args.command)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
