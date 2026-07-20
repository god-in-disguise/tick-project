from __future__ import annotations

import threading
from decimal import Decimal
from typing import Any


class FakeConnector:
    name = "fake"
    feed_pairs = ("BTC-USD",)

    def __init__(self):
        self._lock = threading.Lock()
        self.balance = 100.0
        self.position: dict[str, Any] | None = None
        self.price_value = 64000.0

    def wallet_address(self) -> str:
        return "0x0000000000000000000000000000000000000001"

    def account(self) -> dict[str, Any]:
        with self._lock:
            return {
                "address": self.wallet_address(),
                "balances": {"usdc": self.balance, "eth": 1.0, "allowance": "max"},
                "positions": [dict(self.position)] if self.position else [],
            }

    def positions(self) -> dict[str, Any]:
        return self.account()

    def markets(self, limit: int = 10) -> dict[str, Any]:
        return {"timestamp": 1, "markets": [FakeMarkets.opportunity()]}

    def price(self, pair: str) -> dict[str, Any]:
        return {"pair": pair, "price": {"mid": self.price_value, "bid": self.price_value - 1, "ask": self.price_value + 1, "open": True}}

    def prices(self) -> dict[str, dict[str, Any]]:
        self.price_value += 1
        return {"BTC-USD": {"mid": self.price_value, "bid": self.price_value - 1, "ask": self.price_value + 1, "isMarketOpen": True}}

    def chart(self, pair: str, minutes: int = 120) -> dict[str, Any]:
        return {"pair": pair, "points": [63990.0, 64000.0]}

    def estimate_open(self, pair: str, side: str, ticket_usd: Decimal, leverage: Decimal) -> dict[str, Any]:
        return {
            "venue": self.name,
            "pair": pair,
            "side": side,
            "ticketUsd": float(ticket_usd),
            "leverage": float(leverage),
            "notionalUsd": float(ticket_usd * leverage),
            "activeCollateralUsd": float(ticket_usd - Decimal("0.2")),
            "collateralAtRiskUsd": float(ticket_usd),
            "price": self.price_value,
            "estimatedOpenCostUsd": 0.2,
            "estimatedAllInCostUsd": 0.2,
            "estimatedLiquidationPrice": self.price_value * 0.99,
            "feeHurdlePct": 0.02,
            "slippageBps": 100,
        }

    def open_position(
        self,
        pair: str,
        side: str,
        ticket_usd: Decimal,
        leverage: Decimal,
        quote: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self.balance -= float(ticket_usd)
            self.position = {
                "pair": pair,
                "pairId": 0,
                "idx": 0,
                "side": side,
                "entry": self.price_value,
                "mark": self.price_value,
                "collateral": float(ticket_usd - Decimal("0.2")),
                "leverage": float(leverage),
                "pnl": 0.0,
                "roePct": 0.0,
                "openedAt": 1,
            }
            return {"status": "opened", "tx": {"txHash": "0xopen"}, "position": dict(self.position)}

    def estimate_close(self, pair: str) -> dict[str, Any]:
        return {"pair": pair, "estimatedCloseCostUsd": 0.0}

    def close_position(self, pair: str, position: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            self.position = None
            self.balance = 101.0
            return {"status": "closed", "closed": True, "tx": {"txHash": "0xclose"}}

    def approve(self, amount: Decimal | None = None) -> dict[str, Any]:
        return {"status": "confirmed"}


class FakeMarkets:
    @staticmethod
    def opportunity() -> dict[str, Any]:
        return {
            "pair": "BTC-USD",
            "symbol": "BTC",
            "name": "Bitcoin",
            "assetClass": "CRYPTO",
            "feedLabel": "Hot tape",
            "price": 64000.0,
            "move": 0.2,
            "activeTapePct": 0.2,
            "feeHurdlePct": 0.02,
            "activitySurplusPct": 0.18,
            "tradability": 80.0,
            "score": 80.0,
            "cooling": False,
            "maxLeverage": 100.0,
            "suggestedLeverage": 50.0,
            "open": True,
            "points": [63990.0, 64000.0],
        }

    def find(self, pair: str) -> dict[str, Any] | None:
        return self.opportunity() if pair == "BTC-USD" else None
