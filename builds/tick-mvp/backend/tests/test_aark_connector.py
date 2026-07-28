from decimal import Decimal

import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data

from tick_mvp.domain.states import TradeSide
from tick_mvp.venues.aark.pricing import estimate_open
from tick_mvp.venues.aark.public import AarkError, AarkMarket
from tick_mvp.venues.aark.signing import address, session_private_key, sign_open


def _market() -> AarkMarket:
    return AarkMarket(
        market_id=2,
        market="AARK-BTC-USD",
        symbol="BTC",
        name="Bitcoin",
        asset_class="CRYPTO",
        index_price=Decimal("63332.08271317"),
        market_price=Decimal("63332.08271317"),
        base_fee_pct=Decimal("0.01"),
        mmr_pct=Decimal("0.04"),
        min_leverage=Decimal("500"),
        max_leverage=Decimal("1000"),
        leverage_steps=(Decimal("500"), Decimal("750"), Decimal("1000")),
        margin_steps=(Decimal("10"), Decimal("50"), Decimal("100")),
        take_profit_cap_pct=Decimal("500"),
        initial_margin_cap_usd=Decimal("500"),
        opening_allowed=True,
        payload={},
    )


def test_live_canary_terms_produce_truthful_open_cost() -> None:
    quote = estimate_open(
        _market(),
        side=TradeSide.LONG,
        ticket_usd=Decimal("10"),
        requested_leverage=Decimal("500"),
        max_loss_usd=Decimal("10"),
        take_profit_usd=None,
        execution_fee_usd=Decimal("0.6"),
        requires_open_challenge=True,
        execution_enabled=True,
    )

    assert quote.notional_usd == Decimal("5000")
    assert quote.estimated_open_cost_usd == Decimal("1.1000")
    assert quote.estimated_round_trip_cost_usd == Decimal("1.1000")
    assert quote.payload["tradingOpenFeeUsd"] == "0.5000"
    assert quote.payload["executionFeeUsd"] == "0.6"
    assert quote.payload["takeProfitPct"] == "100"
    assert quote.take_profit_price == Decimal("63458.74687859634")
    assert quote.opening_allowed is True


def test_aark_1000x_cost_matches_small_ticket_research() -> None:
    quote = estimate_open(
        _market(),
        side=TradeSide.SHORT,
        ticket_usd=Decimal("10"),
        requested_leverage=Decimal("1000"),
        max_loss_usd=Decimal("10"),
        take_profit_usd=None,
        execution_fee_usd=Decimal("0.6"),
        requires_open_challenge=False,
        execution_enabled=True,
    )

    assert quote.notional_usd == Decimal("10000")
    assert quote.estimated_open_cost_usd == Decimal("1.6000")


def test_aark_rejects_unsupported_leverage() -> None:
    with pytest.raises(AarkError, match="supports 500x, 750x, 1000x"):
        estimate_open(
            _market(),
            side=TradeSide.LONG,
            ticket_usd=Decimal("10"),
            requested_leverage=Decimal("600"),
            max_loss_usd=Decimal("10"),
            take_profit_usd=None,
            execution_fee_usd=Decimal("0.6"),
            requires_open_challenge=True,
            execution_enabled=True,
        )


def test_aark_blocks_loss_budget_smaller_than_collateral() -> None:
    quote = estimate_open(
        _market(),
        side=TradeSide.LONG,
        ticket_usd=Decimal("10"),
        requested_leverage=Decimal("500"),
        max_loss_usd=Decimal("5"),
        take_profit_usd=None,
        execution_fee_usd=Decimal("0.6"),
        requires_open_challenge=True,
        execution_enabled=True,
    )

    assert quote.opening_allowed is False
    assert quote.payload["openingBlockedReason"] == "native_stop_loss_unavailable"


def test_open_signature_recovers_registered_delegate() -> None:
    wallet_private_key = "0x" + "11" * 32
    delegate_private_key = session_private_key(wallet_private_key)
    user = Account.from_key(wallet_private_key).address
    nonce = 1_785_228_885_000
    fields = [
        {"name": "user", "type": "address"},
        {"name": "marketId", "type": "uint32"},
        {"name": "amountIn", "type": "uint256"},
        {"name": "leverage", "type": "uint256"},
        {"name": "creditToUse", "type": "uint256"},
        {"name": "takeProfit", "type": "uint256"},
        {"name": "isLong", "type": "bool"},
        {"name": "nonce", "type": "uint256"},
    ]
    values = {
        "user": user,
        "marketId": 2,
        "amountIn": 10 * 10**18,
        "leverage": 500,
        "creditToUse": 0,
        "takeProfit": 100,
        "isLong": True,
        "nonce": nonce,
    }
    signature = sign_open(
        delegate_private_key,
        chain_id=42161,
        user=user,
        market_id=2,
        amount_in=10 * 10**18,
        leverage=500,
        credit_to_use=0,
        take_profit=100,
        is_long=True,
        nonce=nonce,
    )
    message = encode_typed_data(
        domain_data={"name": "AARK", "chainId": 42161},
        message_types={"MoonOrder": fields},
        message_data=values,
    )

    recovered = Account.recover_message(message, signature=signature)

    assert recovered == address(delegate_private_key)
