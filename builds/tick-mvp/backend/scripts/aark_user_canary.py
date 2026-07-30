from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eth_account import Account

from tick_mvp.core.config import Settings, get_settings
from tick_mvp.domain.states import TradeSide
from tick_mvp.infrastructure.custody import PrivateKeyCipher
from tick_mvp.infrastructure.database import create_session_factory, session_scope
from tick_mvp.infrastructure.models import User, WalletAccount
from tick_mvp.venues.aark.api import AarkApiClient
from tick_mvp.venues.aark.pricing import estimate_open
from tick_mvp.venues.aark.public import AarkPublicClient
from tick_mvp.venues.aark.signing import (
    MillisecondNonce,
    address,
    session_private_key,
    sign_close_eip191,
    sign_open,
    sign_open_eip191,
)
from tick_mvp.venues.aark.wallet import AarkWalletExecutor


class EventMonitor:
    def __init__(self, url: str, address: str, chain_id: int) -> None:
        self._url = url
        self._address = address
        self._chain_id = chain_id
        self._started_at = time.monotonic()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self.events: list[dict[str, Any]] = []
        self.error: str | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="aark-canary-events", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        try:
            import socketio

            client = socketio.Client(reconnection=False, logger=False, engineio_logger=False)

            @client.on("message")
            def on_message(payload: Any) -> None:
                received_at = time.monotonic()
                self.events.append(
                    {
                        "elapsedMs": round((received_at - self._started_at) * 1000, 1),
                        "event": _event_name(payload),
                        "payload": payload,
                    }
                )

            client.connect(
                self._url.replace("wss://", "https://").replace("ws://", "http://"),
                socketio_path="ws",
                transports=["websocket"],
                wait_timeout=5,
            )
            client.emit(
                "subscribe",
                {
                    "method": "moon.trade",
                    "params": [self._address, self._chain_id],
                },
            )
            self._ready.set()
            while not self._stop.wait(0.2):
                if not client.connected:
                    break
            if client.connected:
                client.emit(
                    "unsubscribe",
                    {
                        "method": "moon.trade",
                        "params": [self._address, self._chain_id],
                    },
                )
                client.disconnect()
        except Exception as exc:
            self.error = str(exc)
            self._ready.set()


def main() -> None:
    args = parse_args()
    settings = replace(
        get_settings(),
        aark_real_execution_enabled=True,
        aark_auto_deposit_usdc=True,
    )
    private_key = load_private_key(args.user_email, settings.custody_private_key_encryption_key)
    account = Account.from_key(private_key)
    public = AarkPublicClient(settings)
    executor = AarkWalletExecutor(settings, public)
    output: dict[str, Any] = {
        "action": args.action,
        "startedAt": datetime.now(UTC).isoformat(),
        "wallet": account.address,
        "market": args.market,
        "marginUsd": str(args.margin_usd),
        "leverage": str(args.leverage),
    }
    try:
        output["before"] = snapshot(public, account.address, args.market)
        if args.action == "status":
            print(json.dumps(output, indent=2, default=str))
            return

        if args.action in {"prepare", "roundtrip"}:
            started = time.monotonic()
            output["preparation"] = executor.prepare_wallet(private_key, args.deposit_usd)
            output["preparationMs"] = elapsed_ms(started)

        if args.action == "request":
            market = public.market(args.market)
            delegate_key = session_private_key(private_key)
            nonce = MillisecondNonce().next()
            amount_in = int(args.margin_usd * Decimal(10**18))
            signature = _open_signature(
                args.signature_scheme,
                delegate_key,
                chain_id=settings.arb_chain_id,
                user=account.address,
                market_id=market.market_id,
                amount_in=amount_in,
                leverage=int(args.leverage),
                credit_to_use=0,
                take_profit=100,
                is_long=args.side == TradeSide.LONG,
                nonce=nonce,
            )
            output["openRequest"] = {
                "url": f"{settings.aark_api_url.rstrip('/')}/oct/moon/open",
                "headers": {
                    "signature": signature,
                },
                "body": {
                    "chainId": settings.arb_chain_id,
                    "user": account.address,
                    "delegatee": address(delegate_key),
                    "nonce": nonce,
                    "marketId": market.market_id,
                    "isLong": args.side == TradeSide.LONG,
                    "amountIn": str(amount_in),
                    "leverage": str(int(args.leverage)),
                    "credit": "0",
                    "takeProfit": "100",
                    "mode": settings.aark_mode,
                },
            }
            if args.signature_scheme == "live_eip712":
                output["openRequest"]["headers"]["version"] = settings.aark_frontend_version
            if args.request_base64_only:
                encoded = base64.b64encode(
                    json.dumps(output["openRequest"], separators=(",", ":")).encode()
                ).decode()
                print(encoded)
                return

        if args.action == "roundtrip":
            token = os.getenv("AARK_RECAPTCHA_TOKEN", "")
            if not token:
                raise RuntimeError("AARK_RECAPTCHA_TOKEN is required for a live roundtrip")
            market = public.market(args.market)
            quote = estimate_open(
                market,
                side=args.side,
                ticket_usd=args.margin_usd,
                requested_leverage=args.leverage,
                max_loss_usd=args.margin_usd,
                take_profit_usd=None,
                execution_fee_usd=public.execution_fee_usd(),
                requires_open_challenge=True,
                execution_enabled=True,
            )
            quote_payload = dict(quote.payload)
            quote_payload["takeProfitPct"] = "100"
            quote_payload["openChallengeToken"] = token
            monitor = EventMonitor(settings.aark_ws_url, account.address, settings.arb_chain_id)
            monitor.start()
            try:
                open_started = time.monotonic()
                open_result = executor.open_position(
                    private_key_hex=private_key,
                    market=market,
                    side=args.side,
                    ticket_usd=args.margin_usd,
                    leverage=args.leverage,
                    quote_payload=quote_payload,
                    stop_loss_price=None,
                    take_profit_price=None,
                )
                output["openVisibleMs"] = elapsed_ms(open_started)
                output["open"] = _open_result(open_result)
                time.sleep(args.hold_seconds)
                close_started = time.monotonic()
                close_result = executor.close_position(
                    private_key_hex=private_key,
                    market=market,
                    side=args.side,
                    venue_position_id=open_result.venue_position_id,
                )
                output["closeVisibleMs"] = elapsed_ms(close_started)
                output["close"] = _close_result(close_result)
            finally:
                time.sleep(1)
                monitor.stop()
                output["websocket"] = {
                    "error": monitor.error,
                    "events": monitor.events,
                }

        if args.action == "close":
            close_lookup_started = time.monotonic()
            positions = public.positions(account.address)
            while not positions and time.monotonic() - close_lookup_started < 8:
                time.sleep(0.2)
                positions = public.positions(account.address)
            output["closeLookupMs"] = elapsed_ms(close_lookup_started)
            if not positions:
                output["close"] = None
            else:
                position = positions[0]
                market_id = int(position.get("marketId") or position.get("market") or 0)
                market = next(
                    (
                        public.market(item)
                        for item in [args.market]
                        if public.market(item).market_id == market_id
                    ),
                    public.market(args.market),
                )
                venue_position_id = str(
                    position.get("moonIndex")
                    or position.get("moon_index")
                    or position.get("index")
                )
                close_started = time.monotonic()
                if args.signature_scheme == "documented_eip191":
                    close_result = _documented_close(
                        settings=settings,
                        public=public,
                        private_key=private_key,
                        user=account.address,
                        venue_position_id=venue_position_id,
                    )
                else:
                    close_result = executor.close_position(
                        private_key_hex=private_key,
                        market=market,
                        side=args.side,
                        venue_position_id=venue_position_id,
                    )
                output["closeVisibleMs"] = elapsed_ms(close_started)
                output["close"] = (
                    close_result
                    if isinstance(close_result, dict)
                    else _close_result(close_result)
                )

        if args.action == "withdraw" or (args.action == "roundtrip" and args.withdraw_after):
            withdraw_started = time.monotonic()
            output["withdrawal"] = executor.withdraw_to_platform_wallet(private_key)
            output["withdrawalMs"] = elapsed_ms(withdraw_started)

        output["after"] = snapshot(public, account.address, args.market)
        output["finishedAt"] = datetime.now(UTC).isoformat()
        print(json.dumps(output, indent=2, default=str))
    except Exception as exc:
        output["error"] = f"{type(exc).__name__}: {exc}"
        try:
            output["afterError"] = snapshot(public, account.address, args.market)
        except Exception as snapshot_exc:
            output["snapshotError"] = str(snapshot_exc)
        print(json.dumps(output, indent=2, default=str))
        raise
    finally:
        executor.stop()
        public.stop()


def load_private_key(user_email: str, encryption_key: str) -> str:
    canary_private_key = os.getenv("AARK_CANARY_PRIVATE_KEY")
    if canary_private_key:
        return canary_private_key
    session_factory = create_session_factory()
    with session_scope(session_factory) as session:
        row = (
            session.query(WalletAccount)
            .join(User, User.id == WalletAccount.user_id)
            .filter(User.email == user_email)
            .order_by(WalletAccount.created_at.asc())
            .first()
        )
        if row is None or row.encrypted_private_key is None:
            raise RuntimeError(f"funded platform wallet not found for {user_email}")
        encrypted = bytes(row.encrypted_private_key)
    return PrivateKeyCipher(encryption_key).decrypt(encrypted)


def snapshot(public: AarkPublicClient, address: str, market_name: str) -> dict[str, Any]:
    market = public.market(market_name)
    return {
        "venueBalanceUsd": str(public.account_balance_usd(address)),
        "positions": public.positions(address),
        "history": public.trade_history(address)[:3],
        "indexPrice": str(market.index_price),
        "executionFeeUsd": str(public.execution_fee_usd()),
    }


def _open_result(result: Any) -> dict[str, Any]:
    return {
        "status": result.status,
        "venuePositionId": result.venue_position_id,
        "entryPrice": str(result.entry_price),
        "liquidationPrice": str(result.liquidation_price) if result.liquidation_price else None,
        "accountBalanceBeforeUsd": str(result.account_balance_before_usd),
        "txHash": result.tx.tx_hash,
        "payload": result.payload,
    }


def _close_result(result: Any) -> dict[str, Any]:
    return {
        "status": result.status,
        "venueRealizedPnlUsd": (
            str(result.venue_realized_pnl_usd)
            if result.venue_realized_pnl_usd is not None
            else None
        ),
        "accountBalanceAfterUsd": str(result.account_balance_after_usd),
        "closeCashflowUsd": str(result.close_cashflow_usd) if result.close_cashflow_usd else None,
        "txHash": result.tx.tx_hash,
        "payload": result.payload,
    }


def _event_name(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("event", "type", "method", "name"):
        if payload.get(key):
            return str(payload[key])
    data = payload.get("data")
    return _event_name(data) if isinstance(data, dict) else None


def elapsed_ms(started: float) -> float:
    return round((time.monotonic() - started) * 1000, 1)


def _open_signature(
    scheme: str,
    private_key: str,
    **terms: Any,
) -> str:
    if scheme == "documented_eip191":
        terms.pop("chain_id")
        return sign_open_eip191(private_key, **terms)
    return sign_open(private_key, **terms)


def _documented_close(
    *,
    settings: Settings,
    public: AarkPublicClient,
    private_key: str,
    user: str,
    venue_position_id: str,
) -> dict[str, Any]:
    delegate_key = session_private_key(private_key)
    nonce = MillisecondNonce().next()
    moon_index = int(venue_position_id)
    signature = sign_close_eip191(
        delegate_key,
        user=user,
        moon_index=moon_index,
        nonce=nonce,
    )
    api = AarkApiClient(settings)
    try:
        response = api.post(
            "/oct/moon/close",
            body={
                "chainId": settings.arb_chain_id,
                "user": user,
                "delegatee": address(delegate_key),
                "moonIndex": moon_index,
                "nonce": nonce,
                "mode": settings.aark_mode,
            },
            headers={"signature": signature},
            include_frontend_version=False,
        )
        deadline = time.monotonic() + settings.aark_close_wait_seconds
        while time.monotonic() < deadline:
            if not any(
                str(row.get("moonIndex") or row.get("index")) == venue_position_id
                for row in public.positions(user)
            ):
                return {
                    "status": "closed",
                    "signatureScheme": "documented_eip191",
                    "venuePositionId": venue_position_id,
                    "request": response,
                    "venueBalanceUsd": str(public.account_balance_usd(user)),
                    "history": public.trade_history(user)[:3],
                }
            time.sleep(settings.aark_rest_poll_seconds)
        raise RuntimeError(
            f"documented EIP-191 close was accepted but position {venue_position_id} remained open"
        )
    finally:
        api.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aark self-serve live canary.")
    parser.add_argument(
        "action",
        choices=("status", "prepare", "request", "roundtrip", "close", "withdraw"),
    )
    parser.add_argument("--user-email", default="funded-dev@dev.tick.local")
    parser.add_argument("--market", default="AARK-BTC-USD")
    parser.add_argument("--margin-usd", type=Decimal, default=Decimal("10"))
    parser.add_argument("--deposit-usd", type=Decimal, default=Decimal("12"))
    parser.add_argument("--leverage", type=Decimal, default=Decimal("500"))
    parser.add_argument("--side", type=TradeSide, choices=list(TradeSide), default=TradeSide.LONG)
    parser.add_argument("--hold-seconds", type=float, default=1.0)
    parser.add_argument("--withdraw-after", action="store_true")
    parser.add_argument("--request-base64-only", action="store_true")
    parser.add_argument(
        "--signature-scheme",
        choices=("live_eip712", "documented_eip191"),
        default="live_eip712",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
