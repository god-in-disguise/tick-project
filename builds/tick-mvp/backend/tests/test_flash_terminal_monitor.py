from __future__ import annotations

import asyncio
from decimal import Decimal

from tick_mvp.core.config import Settings
from tick_mvp.domain.states import PositionStatus
from tick_mvp.execution.terminal_reducer import TrackedPosition
from tick_mvp.venues.flash.terminal_monitor import (
    FlashTerminalMonitor,
    _terminal_reason,
)


MARKET_KEY = "GGV4VHTAEyWGyGubXTiQZiPajCEtGv2Ed2G2BHmY3zNZ"
BASKET = "2PbGy3LScGoJWZ68nxTpSDLUGtw4y1WggX4XJaaHQUR3"


class FakeFlashClient:
    def __init__(self, *, owner_state: dict, raw_basket: dict) -> None:
        self.owner_state = owner_state
        self.raw_state = raw_basket
        self.closed = False

    def owner(self, _owner: str) -> dict:
        return self.owner_state

    def raw_basket(self, _basket: str) -> dict:
        return self.raw_state

    def close(self) -> None:
        self.closed = True


class FakeReducer:
    def __init__(self, position: TrackedPosition) -> None:
        self.position = position
        self.metrics: list[dict] = []
        self.events = []
        self.reconciliations: list[tuple[str, Decimal]] = []

    def active_positions(self, venue: str = "gtrade") -> list[TrackedPosition]:
        return [self.position] if venue == "flash" else []

    def observe_live_position(self, _position_id: str, **kwargs) -> bool:
        self.metrics.append(kwargs)
        return True

    def apply(self, event, *, defer_to_active_close: bool = False) -> str | None:
        self.events.append((event, defer_to_active_close))
        return self.position.id

    def reconcile_wallet(self, position_id: str, balance: Decimal) -> Decimal:
        self.reconciliations.append((position_id, balance))
        return balance


def _tracked(**overrides) -> TrackedPosition:
    values = {
        "id": "pos_flash",
        "owner": "owner",
        "venue_position_id": f"{BASKET}:{MARKET_KEY}",
        "venue": "flash",
        "market": "FLASH-BTC-USD",
        "side": "long",
        "status": PositionStatus.OPEN,
        "ticket_usd": Decimal("10"),
        "liquidation_price": Decimal("99"),
        "account_balance_before_usd": Decimal("50"),
    }
    values.update(overrides)
    return TrackedPosition(**values)


def test_live_metrics_refresh_fee_aware_pnl_and_liquidation() -> None:
    position = _tracked()
    reducer = FakeReducer(position)
    client = FakeFlashClient(
        owner_state={
            "positionMetrics": {
                MARKET_KEY: {
                    "marketSymbol": "BTC",
                    "sideUi": "Long",
                    "liquidationPriceUi": "98.75",
                    "pnlWithFeeUsdUi": "1.23",
                }
            }
        },
        raw_basket={},
    )
    monitor = FlashTerminalMonitor(
        Settings(),
        reducer=reducer,
        client_factory=lambda: client,
    )

    assert asyncio.run(monitor.check_once()) == 0
    assert reducer.metrics[0]["metrics"]["pnlWithFeeUsdUi"] == "1.23"
    assert reducer.metrics[0]["liquidation_price"] == Decimal("98.75")
    assert reducer.events == []


def test_absent_position_requires_confirmation_then_reconciles() -> None:
    position = _tracked()
    reducer = FakeReducer(position)
    client = FakeFlashClient(
        owner_state={"positionMetrics": {}},
        raw_basket={
            "source": "er",
            "account": {
                "positions": [],
                "debits": [{"mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "amount": 49_000_000}],
                "pendingCredits": [],
            },
        },
    )
    monitor = FlashTerminalMonitor(
        Settings(),
        reducer=reducer,
        client_factory=lambda: client,
    )

    assert asyncio.run(monitor.check_once()) == 0
    assert reducer.events == []
    assert asyncio.run(monitor.check_once()) == 1
    event, deferred = reducer.events[0]
    assert deferred is True
    assert event.reason == "external_close"
    assert event.status == PositionStatus.CLOSED
    assert reducer.reconciliations == [(position.id, Decimal("49.000000"))]


def test_wallet_loss_classifies_restart_recovery_as_liquidation() -> None:
    assert _terminal_reason(
        _tracked(),
        last_metrics=None,
        account_balance_after=Decimal("40"),
    ) == "liquidation"


def test_crossed_flash_liquidation_price_is_authoritative_risk_evidence() -> None:
    assert _terminal_reason(
        _tracked(side="short"),
        last_metrics={
            "exitPrice": {"price": "10100", "exponent": "-2"},
            "liquidationPriceUi": "100",
        },
        account_balance_after=Decimal("49"),
    ) == "liquidation"
