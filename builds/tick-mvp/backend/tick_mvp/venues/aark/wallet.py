from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from eth_account import Account

from tick_mvp.core.config import Settings
from tick_mvp.domain.states import TradeSide
from tick_mvp.venues.aark.api import AarkApiClient
from tick_mvp.venues.aark.constants import AARK_MARGIN_DECIMALS, AARK_USDC_DECIMALS
from tick_mvp.venues.aark.public import AarkError, AarkMarket, AarkPublicClient
from tick_mvp.venues.aark.signing import (
    MillisecondNonce,
    address,
    partner_headers,
    session_private_key,
    sign_close,
    sign_delegate,
    sign_deposit,
    sign_open,
    sign_usdc_permit,
    sign_withdraw,
)
from tick_mvp.venues.base import (
    TransactionPreparedHandler,
    VenueCloseResult,
    VenueOpenResult,
    VenueTxResult,
)


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
OCT_ROUTER_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "user", "type": "address"}],
        "name": "getDelegatee",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    }
]
USDC_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "owner", "type": "address"}],
        "name": "nonces",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]


class AarkWalletExecutor:
    def __init__(self, settings: Settings, public: AarkPublicClient) -> None:
        self._settings = settings
        self._public = public
        self._api = AarkApiClient(settings)
        self._nonce = MillisecondNonce()
        self._web3 = None
        self._router = None
        self._usdc = None

    def start(self) -> None:
        return None

    def stop(self) -> None:
        self._api.close()

    def collateral_balance_usd(self, private_key_hex: str) -> Decimal:
        return self._public.account_balance_usd(Account.from_key(private_key_hex).address)

    def withdraw_to_platform_wallet(
        self,
        private_key_hex: str,
        amount_usd: Decimal | None = None,
    ) -> dict[str, Any]:
        user = Account.from_key(private_key_hex).address
        available = self._public.account_balance_usd(user)
        amount = available if amount_usd is None else min(amount_usd, available)
        units = int(amount * Decimal(10**AARK_USDC_DECIMALS))
        if units <= 0:
            return {
                "venue": "aark",
                "withdrawnUsd": "0",
                "venueBalanceUsd": str(available),
                "request": None,
            }
        nonce = self._nonce.next()
        token = self._checksum(self._settings.aark_usdc_address)
        signature = sign_withdraw(
            private_key_hex,
            chain_id=self._settings.arb_chain_id,
            user=user,
            recipient=user,
            token_address=token,
            amount=units,
            nonce=nonce,
        )
        response = self._api.post(
            "/oct/withdraw",
            body={
                "chainId": self._settings.arb_chain_id,
                "user": user,
                "recipient": user,
                "token": token,
                "amount": str(units),
                "nonce": nonce,
                "isLp": False,
                "mode": self._settings.aark_mode,
            },
            headers={"signature": signature},
        )
        remaining = self._wait_for_balance_below(
            user,
            maximum=available,
            timeout=self._settings.aark_close_wait_seconds,
        )
        return {
            "venue": "aark",
            "withdrawnUsd": str(amount),
            "venueBalanceUsd": str(remaining),
            "request": response,
        }

    def prepare_wallet(
        self,
        private_key_hex: str,
        required_collateral_usd: Decimal,
    ) -> dict[str, Any]:
        user = Account.from_key(private_key_hex).address
        delegate_key = session_private_key(private_key_hex)
        delegatee = address(delegate_key)
        self._ensure_delegate(
            private_key_hex=private_key_hex,
            user=user,
            delegatee=delegatee,
        )
        current = self._public.account_balance_usd(user)
        deposited = Decimal(0)
        if current < required_collateral_usd and self._settings.aark_auto_deposit_usdc:
            deposited = self._deposit(
                private_key_hex=private_key_hex,
                user=user,
                amount_usd=required_collateral_usd - current,
            )
            current = self._wait_for_balance(
                user,
                minimum=required_collateral_usd,
                timeout=self._settings.aark_open_wait_seconds,
            )
        return {
            "venue": "aark",
            "delegatee": delegatee,
            "venueBalanceUsd": str(current),
            "depositedUsd": str(deposited),
            "collateralReady": current >= required_collateral_usd,
            "autoDepositEnabled": self._settings.aark_auto_deposit_usdc,
        }

    def open_position(
        self,
        *,
        private_key_hex: str,
        market: AarkMarket,
        side: TradeSide,
        ticket_usd: Decimal,
        leverage: Decimal,
        quote_payload: dict[str, Any],
        stop_loss_price: Decimal | None,
        take_profit_price: Decimal | None,
        on_transaction_prepared: TransactionPreparedHandler | None = None,
    ) -> VenueOpenResult:
        del stop_loss_price, take_profit_price, on_transaction_prepared
        self._ensure_live_enabled()
        user = Account.from_key(private_key_hex).address
        delegate_key = session_private_key(private_key_hex)
        delegatee = address(delegate_key)
        required = ticket_usd + Decimal(str(quote_payload.get("tradingOpenFeeUsd") or 0))
        required += Decimal(str(quote_payload.get("executionFeeUsd") or 0))
        preparation = self.prepare_wallet(private_key_hex, required)
        if not bool(preparation["collateralReady"]):
            raise AarkError(
                f"Aark venue balance requires ${required}; enable auto-deposit or fund Aark first"
            )

        before_balance = self._public.account_balance_usd(user)
        before_ids = {
            _position_id(row)
            for row in self._public.positions(user)
            if _position_id(row) is not None
        }
        nonce = self._nonce.next()
        amount_in = int(ticket_usd * Decimal(10**AARK_MARGIN_DECIMALS))
        take_profit = int(Decimal(str(quote_payload.get("takeProfitPct") or 100)))
        signature = sign_open(
            delegate_key,
            chain_id=self._settings.arb_chain_id,
            user=user,
            market_id=market.market_id,
            amount_in=amount_in,
            leverage=int(leverage),
            credit_to_use=0,
            take_profit=take_profit,
            is_long=side == TradeSide.LONG,
            nonce=nonce,
        )
        headers = {"signature": signature}
        challenge = str(quote_payload.get("openChallengeToken") or "")
        if self._settings.aark_partner_private_key:
            headers.update(partner_headers(self._settings.aark_partner_private_key))
        elif challenge:
            headers["recaptcha-response"] = challenge
        else:
            raise AarkError("Aark open requires a fresh reCAPTCHA token or registered partner key")

        response = self._api.post(
            "/oct/moon/open",
            body={
                "chainId": self._settings.arb_chain_id,
                "user": user,
                "delegatee": delegatee,
                "nonce": nonce,
                "marketId": market.market_id,
                "isLong": side == TradeSide.LONG,
                "amountIn": str(amount_in),
                "leverage": str(int(leverage)),
                "credit": "0",
                "takeProfit": str(take_profit),
                "mode": self._settings.aark_mode,
            },
            headers=headers,
        )
        try:
            position = self._wait_for_new_position(
                user=user,
                before_ids=before_ids,
                market_id=market.market_id,
                side=side,
            )
        except AarkError as exc:
            raise AarkError(
                f"{exc}; accepted_request={response}"
            ) from exc
        venue_position_id = _position_id(position)
        tx_hash = _first(position, "openTxHash", "txHash", "transactionHash")
        tx_hash = str(tx_hash) if tx_hash else self._api.transaction_hash(response)
        return VenueOpenResult(
            status="open",
            tx=_gasless_tx(
                tx_hash=tx_hash,
                nonce=nonce,
                payload={"request": response, "position": position, "gasless": True},
            ),
            venue_position_id=venue_position_id,
            entry_price=_decimal(position, "entryPrice", "openPrice", "indexPrice") or market.index_price,
            liquidation_price=_decimal(position, "liquidationPrice", "liqPrice"),
            stop_loss_price=None,
            take_profit_price=_decimal(position, "takeProfitPrice", "tpPrice"),
            opened_at=_datetime(position, "openedAt", "createdAt", "timestamp") or datetime.now(UTC),
            account_balance_before_usd=before_balance,
            payload={
                "request": response,
                "position": position,
                "delegatee": delegatee,
                "walletPreparation": preparation,
            },
        )

    def close_position(
        self,
        *,
        private_key_hex: str,
        market: AarkMarket,
        side: TradeSide,
        venue_position_id: str | None,
        on_transaction_prepared: TransactionPreparedHandler | None = None,
    ) -> VenueCloseResult:
        del market, side, on_transaction_prepared
        self._ensure_live_enabled()
        if venue_position_id is None:
            raise AarkError("Aark close requires a moon position index")
        user = Account.from_key(private_key_hex).address
        delegate_key = session_private_key(private_key_hex)
        delegatee = address(delegate_key)
        nonce = self._nonce.next()
        moon_index = int(venue_position_id)
        signature = sign_close(
            delegate_key,
            chain_id=self._settings.arb_chain_id,
            user=user,
            moon_index=moon_index,
            nonce=nonce,
        )
        response = self._api.post(
            "/oct/moon/close",
            body={
                "chainId": self._settings.arb_chain_id,
                "user": user,
                "delegatee": delegatee,
                "moonIndex": moon_index,
                "nonce": nonce,
                "mode": self._settings.aark_mode,
            },
            headers={"signature": signature},
        )
        self._wait_until_closed(user, venue_position_id)
        balance = self._public.account_balance_usd(user)
        history = self._matching_history(user, venue_position_id)
        tx_hash = _first(history, "closeTxHash", "txHash", "transactionHash")
        tx_hash = str(tx_hash) if tx_hash else self._api.transaction_hash(response)
        return VenueCloseResult(
            status="closed",
            tx=_gasless_tx(
                tx_hash=tx_hash,
                nonce=nonce,
                payload={"request": response, "history": history, "gasless": True},
            ),
            closed_at=_datetime(history, "closedAt", "updatedAt", "timestamp") or datetime.now(UTC),
            venue_realized_pnl_usd=_decimal(history, "pnlNet", "pnl", "realizedPnl"),
            account_balance_after_usd=balance,
            close_cashflow_usd=_decimal(history, "returnedCollateral", "amountSentToUser"),
            payload={"request": response, "history": history},
        )

    def _ensure_delegate(self, *, private_key_hex: str, user: str, delegatee: str) -> None:
        current = self._delegatee(user)
        if current.lower() == delegatee.lower():
            return
        nonce = self._nonce.next()
        signature = sign_delegate(
            private_key_hex,
            chain_id=self._settings.arb_chain_id,
            delegator=user,
            delegatee=delegatee,
            nonce=nonce,
        )
        self._api.post(
            "/oct/delegate",
            body={
                "chainId": self._settings.arb_chain_id,
                "delegator": user,
                "delegatee": delegatee,
                "nonce": nonce,
                "mode": self._settings.aark_mode,
            },
            headers={"signature": signature},
        )
        deadline = time.monotonic() + self._settings.aark_open_wait_seconds
        while time.monotonic() < deadline:
            if self._delegatee(user).lower() == delegatee.lower():
                return
            self._api.wait(self._settings.aark_rest_poll_seconds)
        raise AarkError("Aark delegate request was accepted but did not become active before timeout")

    def _deposit(self, *, private_key_hex: str, user: str, amount_usd: Decimal) -> Decimal:
        units = int(amount_usd * Decimal(10**AARK_USDC_DECIMALS))
        if units <= 0:
            return Decimal(0)
        onchain_balance = int(self._usdc_contract().functions.balanceOf(self._checksum(user)).call())
        if onchain_balance < units:
            raise AarkError("insufficient wallet USDC for Aark deposit")
        permit_nonce = int(self._usdc_contract().functions.nonces(self._checksum(user)).call())
        deadline = int(time.time()) + 120
        deposit_nonce = self._nonce.next()
        permit_signature = sign_usdc_permit(
            private_key_hex,
            chain_id=self._settings.arb_chain_id,
            token_address=self._checksum(self._settings.aark_usdc_address),
            token_name="USD Coin",
            token_version="2",
            owner=user,
            spender=self._checksum(self._settings.aark_vault_address),
            value=units,
            nonce=permit_nonce,
            deadline=deadline,
        )
        deposit_signature = sign_deposit(
            private_key_hex,
            chain_id=self._settings.arb_chain_id,
            payor=user,
            user=user,
            token_address=self._checksum(self._settings.aark_usdc_address),
            amount=units,
            nonce=deposit_nonce,
        )
        self._api.post(
            "/oct/deposit",
            body={
                "chainId": self._settings.arb_chain_id,
                "user": user,
                "token": self._checksum(self._settings.aark_usdc_address),
                "amount": str(units),
                "deadline": deadline,
                "nonce": deposit_nonce,
                "isLp": False,
                "mode": self._settings.aark_mode,
            },
            headers={
                "signature": permit_signature,
                "deposit-signature": deposit_signature,
            },
        )
        return Decimal(units) / Decimal(10**AARK_USDC_DECIMALS)

    def _wait_for_new_position(
        self,
        *,
        user: str,
        before_ids: set[str | None],
        market_id: int,
        side: TradeSide,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + self._settings.aark_open_wait_seconds
        while time.monotonic() < deadline:
            for row in self._public.positions(user):
                row_id = _position_id(row)
                if row_id in before_ids:
                    continue
                if _int(row, "marketId") not in {None, market_id}:
                    continue
                is_long = _bool(row, "isLong", "long")
                if is_long is not None and is_long != (side == TradeSide.LONG):
                    continue
                return row
            self._api.wait(self._settings.aark_rest_poll_seconds)
        raise AarkError("Aark open was accepted but position was not visible before timeout")

    def _wait_until_closed(self, user: str, venue_position_id: str) -> None:
        deadline = time.monotonic() + self._settings.aark_close_wait_seconds
        while time.monotonic() < deadline:
            ids = {_position_id(row) for row in self._public.positions(user)}
            if venue_position_id not in ids:
                return
            self._api.wait(self._settings.aark_rest_poll_seconds)
        raise AarkError("Aark close was accepted but position remained open before timeout")

    def _matching_history(self, user: str, venue_position_id: str) -> dict[str, Any]:
        for row in self._public.trade_history(user):
            if _position_id(row) == venue_position_id:
                return row
        return {}

    def _wait_for_balance(self, user: str, *, minimum: Decimal, timeout: float) -> Decimal:
        deadline = time.monotonic() + timeout
        balance = Decimal(0)
        while time.monotonic() < deadline:
            balance = self._public.account_balance_usd(user)
            if balance >= minimum:
                return balance
            self._api.wait(self._settings.aark_rest_poll_seconds)
        return balance

    def _wait_for_balance_below(self, user: str, *, maximum: Decimal, timeout: float) -> Decimal:
        deadline = time.monotonic() + timeout
        balance = maximum
        while time.monotonic() < deadline:
            balance = self._public.account_balance_usd(user)
            if balance < maximum:
                return balance
            self._api.wait(self._settings.aark_rest_poll_seconds)
        return balance

    def _ensure_live_enabled(self) -> None:
        if not self._settings.aark_real_execution_enabled:
            raise AarkError("AARK_REAL_EXECUTION_ENABLED=false")

    def _delegatee(self, user: str) -> str:
        return str(
            self._router_contract()
            .functions.getDelegatee(self._checksum(user))
            .call()
        )

    def _rpc(self):
        if self._web3 is None:
            if not self._settings.arb_rpc_url:
                raise AarkError("ARB_RPC_URL is required for Aark wallet preparation")
            from web3 import Web3

            self._web3 = Web3(
                Web3.HTTPProvider(
                    self._settings.arb_rpc_url,
                    request_kwargs={"timeout": 15},
                )
            )
        return self._web3

    def _router_contract(self):
        if self._router is None:
            self._router = self._rpc().eth.contract(
                address=self._checksum(self._settings.aark_oct_router_address),
                abi=OCT_ROUTER_ABI,
            )
        return self._router

    def _usdc_contract(self):
        if self._usdc is None:
            self._usdc = self._rpc().eth.contract(
                address=self._checksum(self._settings.aark_usdc_address),
                abi=USDC_ABI,
            )
        return self._usdc

    @staticmethod
    def _checksum(value: str) -> str:
        from web3 import Web3

        return Web3.to_checksum_address(value)


def _gasless_tx(*, tx_hash: str | None, nonce: int, payload: dict[str, Any]) -> VenueTxResult:
    return VenueTxResult(
        status="confirmed",
        tx_hash=tx_hash,
        nonce=nonce,
        block_number=None,
        gas_used=0,
        effective_gas_price=0,
        payload=payload,
    )


def _position_id(row: dict[str, Any]) -> str | None:
    value = _first(row, "moonIndex", "moon_index", "index", "id")
    return str(value) if value is not None else None


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if row.get(key) is not None:
            return row[key]
    return None


def _decimal(row: dict[str, Any], *keys: str) -> Decimal | None:
    value = _first(row, *keys)
    try:
        return Decimal(str(value)) if value is not None else None
    except (ValueError, TypeError):
        return None


def _int(row: dict[str, Any], *keys: str) -> int | None:
    value = _first(row, *keys)
    try:
        return int(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def _bool(row: dict[str, Any], *keys: str) -> bool | None:
    value = _first(row, *keys)
    if value is None:
        return None
    if isinstance(value, str):
        return value.lower() in {"true", "1", "long"}
    return bool(value)


def _datetime(row: dict[str, Any], *keys: str) -> datetime | None:
    value = _first(row, *keys)
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            seconds = float(value) / 1000 if float(value) > 10**12 else float(value)
            return datetime.fromtimestamp(seconds, UTC)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
