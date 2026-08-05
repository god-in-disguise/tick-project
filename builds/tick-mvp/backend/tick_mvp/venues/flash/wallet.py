from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from tick_mvp.domain.states import TradeSide
from tick_mvp.venues.flash.balances import available_collateral_usd
from tick_mvp.venues.base import (
    TransactionPreparedHandler,
    VenueCloseResult,
    VenueOpenResult,
    VenueTxResult,
)
from tick_mvp.venues.flash.client import FlashClient, FlashError
from tick_mvp.venues.flash.constants import USDC_MINT, USD_DECIMALS, market_config
from tick_mvp.venues.flash.funding import FlashSetupFunder
from tick_mvp.venues.flash.signing import keypair_from_secret


class FlashWalletExecutor:
    def __init__(
        self,
        client: FlashClient,
        *,
        slippage_percentage: Decimal,
        setup_funder: FlashSetupFunder | None = None,
    ) -> None:
        self._client = client
        self._slippage_percentage = slippage_percentage
        self._setup_funder = setup_funder
        self._basket_cache: dict[str, str] = {}
        self._raw_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._ready_collateral: dict[str, tuple[float, Decimal]] = {}
        self._preparation_locks: dict[str, threading.Lock] = {}
        self._cache_lock = threading.Lock()

    def prepare_wallet(
        self,
        private_key: str,
        required_collateral_usd: Decimal,
    ) -> dict[str, Any]:
        keypair = keypair_from_secret(private_key)
        owner = str(keypair.pubkey())
        with self._preparation_lock(owner):
            cached = self._ready_collateral.get(owner)
            if (
                self._setup_funder is None
                and
                cached is not None
                and time.monotonic() - cached[0] <= 10
                and cached[1] >= required_collateral_usd
            ):
                return {
                    "allowanceReady": True,
                    "delegationReady": True,
                    "basketPubkey": self._basket_cache[owner],
                    "collateralBalanceUsd": str(cached[1]),
                    "setupSubmitted": False,
                }

            actions: list[dict[str, Any]] = []
            state = self._client.owner(owner)
            basket = state.get("basketPubkey")
            raw = self._client.raw_basket(str(basket)) if basket else {}
            deposited_available = Decimal(0)
            available = Decimal(0)
            setup_funding: dict[str, Any] | None = None
            wallet_usdc: Decimal | None = None
            if self._setup_funder is not None:
                wallet_state = self._setup_funder.wallet_state(owner)
                wallet_usdc = wallet_state.usdc
                deposited_available = wallet_state.deposited_usdc
                available = available_collateral_usd(raw, deposited_available)
                if available + wallet_usdc < required_collateral_usd:
                    return {
                        "allowanceReady": False,
                        "delegationReady": bool(basket and raw.get("source") == "er"),
                        "basketPubkey": str(basket) if basket else None,
                        "collateralBalanceUsd": str(available),
                        "onchainUsdc": str(wallet_usdc),
                        "setupStatus": "awaiting_usdc",
                        "setupSubmitted": False,
                    }
                if not basket or wallet_usdc > 0 or raw.get("source") != "er":
                    setup_funding = self._setup_funder.ensure_funded(
                        owner,
                        target_sol=(
                            self._setup_funder.setup_target_sol
                            if not basket
                            else Decimal("0.005")
                        ),
                    )
            initialized = not basket
            if initialized:
                actions.append(
                    self._prepare_and_submit(
                        "/transaction-builder/init-basket",
                        {"owner": owner},
                        keypair,
                        skip_preflight=False,
                    )
                )
                state = self._wait_owner(owner, lambda value: bool(value.get("basketPubkey")))
                basket = state.get("basketPubkey")
                if not basket:
                    raise FlashError("Flash basket initialization did not become visible")
                actions.append(
                    self._prepare_and_submit(
                        "/transaction-builder/init-deposit-ledger",
                        {"owner": owner},
                        keypair,
                        skip_preflight=False,
                    )
                )
                # Flash's builder needs its simulator to observe the new ledger.
                time.sleep(2)

            basket = str(basket)
            raw = self._client.raw_basket(basket)
            available = available_collateral_usd(raw, deposited_available)

            if raw.get("source") != "er":
                actions.append(
                    self._prepare_and_submit(
                        "/transaction-builder/delegate-basket",
                        {"owner": owner},
                        keypair,
                        skip_preflight=True,
                    )
                )
                raw = self._wait_raw(basket, lambda value: value.get("source") == "er")

            deposit_amount = (
                wallet_usdc
                if wallet_usdc is not None
                else max(Decimal(0), required_collateral_usd - available)
            )
            if deposit_amount > 0:
                actions.append(
                    self._prepare_and_submit(
                        "/transaction-builder/deposit-direct",
                        {
                            "owner": owner,
                            "tokenMint": USDC_MINT,
                            "amount": format(deposit_amount, "f"),
                        },
                        keypair,
                        skip_preflight=False,
                    )
                )
                expected_available = available + deposit_amount
                if self._setup_funder is not None:
                    available, raw = self._wait_venue_collateral(
                        owner,
                        basket,
                        expected_available,
                    )
                else:
                    raw = self._wait_raw(
                        basket,
                        lambda value: available_collateral_usd(
                            value,
                            deposited_available,
                        )
                        >= expected_available,
                    )
                    available = available_collateral_usd(raw, deposited_available)

            if raw.get("source") != "er":
                raw = self._wait_raw(
                    basket,
                    lambda value: value.get("source") == "er",
                )

            self._remember(owner, basket, raw)
            self._ready_collateral[owner] = (time.monotonic(), available)
            return {
                "allowanceReady": available >= required_collateral_usd,
                "delegationReady": raw.get("source") == "er",
                "basketPubkey": basket,
                "collateralBalanceUsd": str(available),
                "rawSource": raw.get("source"),
                "setupSubmitted": bool(actions),
                "setupTransactions": actions,
                "setupFunding": setup_funding,
                "setupStatus": "ready",
            }

    def open_position(
        self,
        *,
        private_key: str,
        market: str,
        side: TradeSide,
        ticket_usd: Decimal,
        leverage: Decimal,
        stop_loss_price: Decimal | None,
        take_profit_price: Decimal | None,
        on_transaction_prepared: TransactionPreparedHandler | None,
    ) -> VenueOpenResult:
        if stop_loss_price is not None or take_profit_price is not None:
            raise FlashError("Flash trigger orders are not certified for TICK execution")
        config = market_config(market)
        if not config.execution_certified:
            raise FlashError(f"{config.symbol} has not passed the Flash execution canary")
        keypair = keypair_from_secret(private_key)
        owner = str(keypair.pubkey())
        basket = self._basket(owner)
        initial = self._snapshot(owner, basket, max_age_seconds=2.0)
        account = initial.get("account") or {}
        if account.get("positions") or account.get("orders"):
            raise FlashError("Flash basket is not empty")
        account_balance_before = available_collateral_usd(
            initial,
            self._deposited_collateral_usd(owner),
        )

        prepared = self._client.prepare(
            "/transaction-builder/open-position",
            {
                "inputTokenSymbol": "USDC",
                "outputTokenSymbol": config.symbol,
                "inputAmountUi": str(ticket_usd),
                "leverage": float(leverage),
                "tradeType": side.value.upper(),
                "orderType": "MARKET",
                "owner": owner,
                "slippagePercentage": str(self._slippage_percentage),
            },
            keypair,
        )
        if on_transaction_prepared is not None:
            on_transaction_prepared(
                prepared.signature,
                None,
                prepared.signed_transaction_base64,
            )
        observation = self._client.submit_and_wait(
            prepared,
            basket_pubkey=basket,
            predicate=lambda snapshot: len(_positions(snapshot)) == 1,
        )
        position = _positions(observation["rawBasket"])[0]
        self._remember(owner, basket, observation["rawBasket"])
        raw = position.get("position") or {}
        entry_price = _price(raw.get("entryPrice"))
        venue_position_id = f"{basket}:{position.get('market')}"
        opened_at = _datetime_from_epoch(raw.get("openTime"))
        return VenueOpenResult(
            status="open",
            tx=_tx_result(prepared.signature, observation),
            venue_position_id=venue_position_id,
            entry_price=entry_price,
            liquidation_price=_optional_decimal(prepared.quote.get("newLiquidationPrice")),
            stop_loss_price=None,
            take_profit_price=None,
            opened_at=opened_at,
            account_balance_before_usd=account_balance_before,
            payload={
                "quote": prepared.quote,
                "position": raw,
                "authoritativeRawBasket": observation["rawBasket"],
                "detectionSource": "flash_raw_basket",
                "visibleMs": observation["visibleMs"],
                "buildMs": prepared.build_ms,
                "signMs": prepared.sign_ms,
                "submitRequestMs": _first_submit_ms(observation),
                "hedged": observation["hedged"],
            },
        )

    def close_position(
        self,
        *,
        private_key: str,
        market: str,
        side: TradeSide,
        venue_position_id: str | None,
        on_transaction_prepared: TransactionPreparedHandler | None,
    ) -> VenueCloseResult:
        config = market_config(market)
        keypair = keypair_from_secret(private_key)
        owner = str(keypair.pubkey())
        basket = self._basket(owner)
        snapshot = self._snapshot(owner, basket)
        position = _single_position(snapshot, venue_position_id)
        size_usd = _position_size_usd(position)
        prepared = self._client.prepare(
            "/transaction-builder/close-position",
            {
                "marketSymbol": config.symbol,
                "side": side.value.upper(),
                "inputUsdUi": format(size_usd, "f"),
                "withdrawTokenSymbol": "USDC",
                "owner": owner,
                "closeAll": True,
                "slippagePercentage": str(self._slippage_percentage),
            },
            keypair,
        )
        if on_transaction_prepared is not None:
            on_transaction_prepared(
                prepared.signature,
                None,
                prepared.signed_transaction_base64,
            )
        observation = self._client.submit_and_wait(
            prepared,
            basket_pubkey=basket,
            predicate=lambda current: not _positions(current),
        )
        self._remember(owner, basket, observation["rawBasket"])
        cashflow = _optional_decimal(prepared.quote.get("receiveTokenAmountUsdUi"))
        return VenueCloseResult(
            status="closed",
            tx=_tx_result(prepared.signature, observation),
            closed_at=datetime.now(UTC),
            venue_realized_pnl_usd=None,
            account_balance_after_usd=None,
            close_cashflow_usd=cashflow,
            payload={
                "quote": prepared.quote,
                "venueSettledPnlUsd": prepared.quote.get("settledPnl"),
                "authoritativeRawBasket": observation["rawBasket"],
                "detectionSource": "flash_raw_basket",
                "visibleMs": observation["visibleMs"],
                "buildMs": prepared.build_ms,
                "signMs": prepared.sign_ms,
                "submitRequestMs": _first_submit_ms(observation),
                "hedged": observation["hedged"],
            },
        )

    def recover_execution(
        self,
        *,
        private_key: str,
        venue_position_id: str | None,
        tx_hash: str,
    ) -> dict[str, Any]:
        keypair = keypair_from_secret(private_key)
        owner = str(keypair.pubkey())
        basket = self._basket(owner)
        snapshot = self._client.raw_basket(basket)
        self._remember(owner, basket, snapshot)
        positions = _positions(snapshot)
        if venue_position_id is None and len(positions) == 1:
            position = positions[0]
            raw = position.get("position") or {}
            return {
                "tx": _tx_result(
                    tx_hash,
                    {"rawBasket": snapshot, "hedged": False},
                ),
                "position": raw,
                "venuePositionId": f"{basket}:{position.get('market')}",
                "entryPrice": str(_price(raw.get("entryPrice"))),
                "openedAt": _datetime_from_epoch(raw.get("openTime")),
                "source": "flash_raw_basket_recovery",
            }
        if venue_position_id is not None and not positions:
            return {
                "tx": _tx_result(
                    tx_hash,
                    {"rawBasket": snapshot, "hedged": False},
                ),
                "position": None,
                "source": "flash_raw_basket_recovery",
            }
        # Submission acknowledgement does not prove economic execution. Keep
        # the attempt UNKNOWN until the intended raw-basket transition exists.
        return {
            "tx": None,
            "position": positions[0] if positions else None,
            "source": "flash_raw_basket_unresolved",
        }

    def collateral_balance_usd(self, private_key: str) -> Decimal:
        keypair = keypair_from_secret(private_key)
        owner = str(keypair.pubkey())
        basket = self._basket(owner)
        snapshot = self._client.raw_basket(basket)
        self._remember(owner, basket, snapshot)
        return available_collateral_usd(
            snapshot,
            self._deposited_collateral_usd(owner),
        )

    def current_liquidation_price(self, *, position: dict[str, Any] | None, **_: Any):
        del position
        return None

    def _basket(self, owner: str) -> str:
        with self._cache_lock:
            cached = self._basket_cache.get(owner)
        if cached:
            return cached
        basket = self._client.owner(owner).get("basketPubkey")
        if not basket:
            raise FlashError("Flash basket is not initialized")
        value = str(basket)
        with self._cache_lock:
            self._basket_cache[owner] = value
        return value

    def _snapshot(
        self,
        owner: str,
        basket: str,
        *,
        max_age_seconds: float | None = None,
    ) -> dict[str, Any]:
        with self._cache_lock:
            cached = self._raw_cache.get(owner)
        if cached is not None:
            observed_at, snapshot = cached
            if max_age_seconds is None or time.monotonic() - observed_at <= max_age_seconds:
                return snapshot
        snapshot = self._client.raw_basket(basket)
        self._remember(owner, basket, snapshot)
        return snapshot

    def _remember(self, owner: str, basket: str, snapshot: dict[str, Any]) -> None:
        with self._cache_lock:
            self._basket_cache[owner] = basket
            self._raw_cache[owner] = (time.monotonic(), snapshot)

    def _preparation_lock(self, owner: str) -> threading.Lock:
        with self._cache_lock:
            return self._preparation_locks.setdefault(owner, threading.Lock())

    def _prepare_and_submit(
        self,
        path: str,
        body: dict[str, Any],
        keypair: Any,
        *,
        skip_preflight: bool,
    ) -> dict[str, Any]:
        prepared = self._client.prepare(path, body, keypair)
        submission = self._client.submit_exact(
            prepared,
            skip_preflight=skip_preflight,
        )
        return {
            "builderPath": path,
            "signature": prepared.signature,
            "buildMs": prepared.build_ms,
            "signMs": prepared.sign_ms,
            "submission": submission,
        }

    def _wait_owner(
        self,
        owner: str,
        predicate: Any,
        *,
        timeout_seconds: float = 30,
    ) -> dict[str, Any]:
        started = time.monotonic()
        latest: dict[str, Any] = {}
        while time.monotonic() - started < timeout_seconds:
            latest = self._client.owner(owner)
            if predicate(latest):
                return latest
            time.sleep(0.25)
        raise FlashError(f"Flash owner state did not converge: {latest}")

    def _wait_raw(
        self,
        basket: str,
        predicate: Any,
        *,
        timeout_seconds: float = 30,
    ) -> dict[str, Any]:
        started = time.monotonic()
        latest: dict[str, Any] = {}
        while time.monotonic() - started < timeout_seconds:
            latest = self._client.raw_basket(basket)
            if predicate(latest):
                return latest
            time.sleep(0.10)
        raise FlashError(f"Flash basket state did not converge: {latest}")

    def _wait_venue_collateral(
        self,
        owner: str,
        basket: str,
        expected: Decimal,
        *,
        timeout_seconds: float = 30,
    ) -> tuple[Decimal, dict[str, Any]]:
        started = time.monotonic()
        latest: dict[str, Any] = {}
        available = Decimal(0)
        while time.monotonic() - started < timeout_seconds:
            latest = self._client.raw_basket(basket)
            available = available_collateral_usd(
                latest,
                self._deposited_collateral_usd(owner),
            )
            if available >= expected:
                return available, latest
            time.sleep(0.10)
        raise FlashError(
            f"Flash collateral did not converge: {available} available, {expected} expected"
        )

    def _deposited_collateral_usd(self, owner: str) -> Decimal:
        if self._setup_funder is None:
            return Decimal(0)
        return self._setup_funder.wallet_state(owner).deposited_usdc


def _positions(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return list((snapshot.get("account") or {}).get("positions") or [])


def _single_position(
    snapshot: dict[str, Any], venue_position_id: str | None
) -> dict[str, Any]:
    positions = _positions(snapshot)
    if len(positions) != 1:
        raise FlashError(f"expected one Flash position, found {len(positions)}")
    position = positions[0]
    if venue_position_id:
        expected_market = venue_position_id.rsplit(":", 1)[-1]
        if str(position.get("market")) != expected_market:
            raise FlashError("Flash raw position does not match the stored position id")
    return position


def _position_size_usd(position: dict[str, Any]) -> Decimal:
    raw_size = (position.get("position") or {}).get("sizeUsd")
    if raw_size is None:
        raise FlashError("Flash raw position is missing sizeUsd")
    return Decimal(str(raw_size)).scaleb(-USD_DECIMALS)


def _price(value: Any) -> Decimal:
    if not isinstance(value, dict):
        raise FlashError("Flash raw position is missing its entry price")
    return Decimal(str(value["price"])) * (Decimal(10) ** int(value["exponent"]))


def _optional_decimal(value: Any) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _datetime_from_epoch(value: Any) -> datetime | None:
    return datetime.fromtimestamp(int(value), UTC) if value is not None else None


def _tx_result(signature: str, observation: dict[str, Any]) -> VenueTxResult:
    return VenueTxResult(
        status="confirmed",
        tx_hash=signature,
        nonce=None,
        block_number=None,
        gas_used=None,
        effective_gas_price=None,
        payload={
            "chain": "solana",
            "executionLayer": "magicblock_er",
            "gasPayer": None,
            "hedged": bool(observation.get("hedged")),
            "buildMs": observation.get("buildMs"),
            "signMs": observation.get("signMs"),
        },
    )


def _first_submit_ms(observation: dict[str, Any]) -> float | None:
    submissions = observation.get("submissions") or []
    if not submissions:
        return None
    value = submissions[0].get("requestMs")
    return float(value) if value is not None else None
