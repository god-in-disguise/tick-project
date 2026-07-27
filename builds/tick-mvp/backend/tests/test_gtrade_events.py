from __future__ import annotations

import json
import time
from decimal import Decimal
from types import SimpleNamespace

from eth_abi import encode

from tick_mvp.core.config import Settings
from tick_mvp.domain.states import PositionStatus
from tick_mvp.venues.gtrade.events import GTradeEventStream
from tick_mvp.venues.gtrade.onchain_events import (
    MARKET_EXECUTED_DATA_TYPES,
    MARKET_EXECUTED_TOPIC,
    decode_execution_log,
)
from tick_mvp.venues.gtrade.price_stream import GTradePriceStream
from tick_mvp.venues.gtrade.terminal_monitor import _terminal_event
from tick_mvp.venues.gtrade.wallet import (
    GTradeWalletExecutor,
    _close_event_financials,
    _event_detail_price,
    _position_stop_loss_price,
)
from tick_mvp.venues.base import VenueTxResult


OWNER_A = "0x1111111111111111111111111111111111111111"
OWNER_B = "0x2222222222222222222222222222222222222222"


def test_event_stream_correlates_each_tracked_user() -> None:
    stream = GTradeEventStream("wss://example.invalid")
    stream.track_owner(OWNER_A)
    stream.track_owner(OWNER_B)
    since = time.time() - 1

    stream._handle_raw(_register_trade(OWNER_A, pair_index=300, position_index=7))
    stream._handle_raw(_register_trade(OWNER_B, pair_index=300, position_index=8))

    first = stream.wait_for_position_event(
        owner=OWNER_A,
        pair_index=300,
        present=True,
        since=since,
        timeout_seconds=0.01,
    )
    second = stream.wait_for_position_event(
        owner=OWNER_B,
        pair_index=300,
        present=True,
        since=since,
        timeout_seconds=0.01,
    )

    assert first["position"]["trade"]["index"] == 7
    assert second["position"]["trade"]["index"] == 8


def test_event_stream_ignores_untracked_wallets() -> None:
    stream = GTradeEventStream("wss://example.invalid")
    stream.track_owner(OWNER_A)

    stream._handle_raw(_register_trade(OWNER_B, pair_index=300, position_index=8))

    assert stream.health()["cachedEvents"] == 0


def test_unregister_can_match_position_index_without_pair() -> None:
    stream = GTradeEventStream("wss://example.invalid")
    stream.track_owner(OWNER_A)
    since = time.time() - 1
    stream._handle_raw(
        json.dumps(
            {
                "name": "unregisterTrade",
                "value": {"user": OWNER_A, "index": 7},
            }
        )
    )

    result = stream.wait_for_position_event(
        owner=OWNER_A,
        pair_index=999,
        position_index=7,
        present=False,
        since=since,
        timeout_seconds=0.01,
    )

    assert result["timedOut"] is False
    assert result["source"] == "gains_backend_ws"


def test_wallet_confirmation_uses_fastest_valid_source(monkeypatch) -> None:
    wallet = GTradeWalletExecutor(Settings())

    def event_wait(**_kwargs):
        time.sleep(0.01)
        return {
            "source": "gains_backend_ws",
            "position": {"trade": {"user": OWNER_A, "pairIndex": 300, "index": 7}},
            "elapsedMs": 10.0,
            "observedPresent": True,
            "timedOut": False,
        }

    def rest_wait(**_kwargs):
        time.sleep(0.15)
        return {
            "source": "gains_open_trades_rest",
            "position": None,
            "elapsedMs": 150.0,
            "observedPresent": None,
            "timedOut": True,
        }

    monkeypatch.setattr(wallet._events, "wait_for_position_event", event_wait)
    monkeypatch.setattr(wallet, "_wait_for_position_rest", rest_wait)

    result = wallet._wait_for_position(
        address=OWNER_A,
        pair_index=300,
        present=True,
        since=time.time() - 1,
        timeout_seconds=0.5,
    )

    assert result["race"]["winner"] == "gains_backend_ws"
    assert result["position"]["trade"]["index"] == 7


def test_direct_market_execution_log_becomes_authoritative_position_event() -> None:
    stream = GTradeEventStream("wss://example.invalid")
    stream.track_owner(OWNER_A)
    trade = (
        OWNER_A,
        7,
        300,
        500_000,
        True,
        True,
        3,
        0,
        10_000_000,
        64_000 * 10**10,
        0,
        63_900 * 10**10,
        False,
        78_125_000_000_000_000,
        0,
    )
    data = encode(
        MARKET_EXECUTED_DATA_TYPES,
        [
            (OWNER_A, 11),
            trade,
            True,
            64_000 * 10**10,
            64_001 * 10**10,
            63_900 * 10**10,
            (78_125_000_000_000_000, 0, 0, 0, 0, 64_001 * 10**10),
            0,
            0,
            100_000_000,
        ],
    )
    event = decode_execution_log(
        {
            "topics": [
                MARKET_EXECUTED_TOPIC,
                _topic_address(OWNER_A),
                _topic_int(7),
            ],
            "data": f"0x{data.hex()}",
            "transactionHash": "0xabc",
            "blockNumber": "0x10",
            "logIndex": "0x2",
        }
    )
    assert event is not None
    event["receivedAt"] = time.time()
    stream._store_event(event)

    result = stream.wait_for_position_event(
        owner=OWNER_A,
        pair_index=300,
        present=True,
        since=time.time() - 1,
        timeout_seconds=0.01,
    )

    assert result["source"] == "gtrade_onchain_ws"
    assert result["position"]["trade"]["index"] == 7
    assert result["event"]["blockNumber"] == 16


def test_price_stream_keeps_latest_real_tick_per_pair() -> None:
    stream = GTradePriceStream("wss://example.invalid")
    stream._handle_raw(json.dumps([300, 64000.1, 313, 3500.2]))

    btc = stream.price(300)
    eth = stream.price(313)

    assert btc is not None and str(btc["mid"]) == "64000.1"
    assert eth is not None and str(eth["mid"]) == "3500.2"


def test_price_stream_records_real_watchlist_observations_with_sequence() -> None:
    stream = GTradePriceStream("wss://example.invalid")
    stream._handle_raw(json.dumps([300, 64000.1, 313, 3500.2]))
    stream._handle_raw(json.dumps([300, 64000.1, 313, 3500.4]))

    btc = stream.snapshot(300)
    eth = stream.snapshot(313, since=1)

    assert [str(item["price"]) for item in btc["ticks"]] == ["64000.1", "64000.1"]
    assert btc["ticks"][1]["unchanged"] is True
    assert [item["sequence"] for item in eth["ticks"]] == [2, 4]
    assert str(eth["latest"]["price"]) == "3500.4"


def test_direct_close_cashflow_produces_immediate_net_result() -> None:
    pnl, cashflow = _close_event_financials(
        {
            "event": {
                "details": {"amountSentToTrader": "7492387"},
                "position": {
                    "trade": {
                        "collateralIndex": 3,
                        "collateralAmount": "10000000",
                    }
                },
            }
        }
    )

    assert str(cashflow) == "7.492387"
    assert str(pnl) == "-2.507613"


def test_open_confirmation_uses_actual_venue_risk_levels() -> None:
    position = {"trade": {"sl": 4_846_519_041_311}}
    position_wait = {
        "event": {"details": {"liquidationPrice": "4846753728828"}}
    }

    assert str(_position_stop_loss_price(position)) == "484.6519041311"
    assert str(_event_detail_price(position_wait, "liquidationPrice")) == "484.6753728828"


def test_wallet_preparation_caches_nonce_and_existing_allowance(monkeypatch) -> None:
    wallet = GTradeWalletExecutor(Settings())
    web3 = SimpleNamespace(
        eth=SimpleNamespace(
            get_transaction_count=lambda _address, _state: 12,
        )
    )
    monkeypatch.setattr(wallet, "_account", lambda _key: (object(), OWNER_A, web3))
    monkeypatch.setattr(wallet._events, "track_owner", lambda _owner: None)
    monkeypatch.setattr(wallet._events, "start", lambda: None)
    monkeypatch.setattr(wallet, "_usdc_allowance", lambda _web3, _address: Decimal("100"))

    result = wallet.prepare_wallet("0x" + "1" * 64, Decimal("10"))

    assert result["allowanceReady"] is True
    assert result["approvalSubmitted"] is False
    assert wallet._nonce_cache[OWNER_A.lower()] == 12
    assert wallet._allowance_cache[OWNER_A.lower()] == Decimal("100")


def test_wallet_preparation_approves_once_before_the_trade(monkeypatch) -> None:
    wallet = GTradeWalletExecutor(Settings())
    web3 = SimpleNamespace(
        eth=SimpleNamespace(
            get_transaction_count=lambda _address, _state: 12,
        )
    )
    monkeypatch.setattr(wallet, "_account", lambda _key: (object(), OWNER_A, web3))
    monkeypatch.setattr(wallet._events, "track_owner", lambda _owner: None)
    monkeypatch.setattr(wallet._events, "start", lambda: None)
    monkeypatch.setattr(wallet, "_usdc_allowance", lambda _web3, _address: Decimal("0"))
    monkeypatch.setattr(wallet, "_prepare_tx_params", lambda _web3, _address: (12, {}))
    monkeypatch.setattr(
        wallet,
        "_approve_usdc",
        lambda _account, _address, prepared: VenueTxResult(
            status="confirmed",
            tx_hash="0xabc",
            nonce=prepared[0],
            block_number=1,
            gas_used=1,
            effective_gas_price=1,
            payload={"label": "approve"},
        ),
    )

    result = wallet.prepare_wallet("0x" + "1" * 64, Decimal("10"))

    assert result["allowanceReady"] is True
    assert result["approvalSubmitted"] is True
    assert wallet._allowance_cache[OWNER_A.lower()] > Decimal("10")


def test_terminal_event_distinguishes_stop_loss_from_liquidation() -> None:
    base = {
        "name": "LimitExecuted",
        "source": "gtrade_onchain_ws",
        "present": False,
        "receivedAt": 1_785_176_993,
        "transactionHash": "0xabc",
        "blockNumber": 123,
        "logIndex": 4,
        "position": {
            "trade": {
                "user": OWNER_A,
                "pairIndex": 452,
                "index": 6,
            }
        },
    }

    stopped = _terminal_event(
        {
            **base,
            "details": {"orderType": 5, "amountSentToTrader": "2219538"},
        }
    )
    liquidated = _terminal_event(
        {
            **base,
            "transactionHash": "0xdef",
            "details": {"orderType": 6, "amountSentToTrader": "0"},
        }
    )

    assert stopped is not None
    assert stopped.reason == "stop_loss"
    assert stopped.status == PositionStatus.CLOSED
    assert stopped.returned_collateral_usd == Decimal("2.219538")
    assert liquidated is not None
    assert liquidated.reason == "liquidation"
    assert liquidated.status == PositionStatus.LIQUIDATED


def _register_trade(owner: str, *, pair_index: int, position_index: int) -> str:
    return json.dumps(
        {
            "name": "registerTrade",
            "value": {
                "trade": {
                    "user": owner,
                    "pairIndex": pair_index,
                    "index": position_index,
                }
            },
        }
    )


def _topic_address(value: str) -> str:
    return f"0x{value.lower().removeprefix('0x').rjust(64, '0')}"


def _topic_int(value: int) -> str:
    return f"0x{value:064x}"
