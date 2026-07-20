from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, Callable

from fastapi import FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import DATABASE_PATH, DEFAULT_LEVERAGE, DEFAULT_TICKET_USD, LOCAL_API_TOKEN
from .connectors import ConnectorError
from .execution import ExecutionError, ExecutionService
from .markets import MarketService
from .registry import build_connector
from .ticks import TickService


LOGGER = logging.getLogger("tick.api")
connector = build_connector()
ticks = TickService(connector, connector.feed_pairs)
market_service = MarketService(connector, ticks)
execution_service = ExecutionService(connector, market_service, DATABASE_PATH)


@asynccontextmanager
async def lifespan(_: FastAPI):
    connector_start = getattr(connector, "start", None)
    connector_stop = getattr(connector, "stop", None)
    if callable(connector_start):
        connector_start()
    ticks.start()
    market_service.start()
    execution_service.start()
    try:
        yield
    finally:
        execution_service.stop()
        market_service.stop()
        ticks.stop()
        if callable(connector_stop):
            connector_stop()


app = FastAPI(title="TICK local canary", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ApproveRequest(BaseModel):
    amount: float | None = None


class QuoteRequest(BaseModel):
    pair: str
    side: str
    ticketUsd: float = Field(default=DEFAULT_TICKET_USD, gt=0)
    leverage: float = Field(default=DEFAULT_LEVERAGE, gt=0)


class OpenRequest(BaseModel):
    quoteId: str
    idempotencyKey: str


class CloseRequest(BaseModel):
    pair: str
    idempotencyKey: str


class LegacyOpenRequest(BaseModel):
    side: str
    leverage: float | None = None
    pair: str | None = None


class LegacyCloseRequest(BaseModel):
    pair: str | None = None


@app.get("/")
def index() -> dict[str, str]:
    return {"name": "TICK local canary", "health": "/api/health"}


@app.get("/api/health")
def health() -> dict[str, Any]:
    execution_health = None
    if hasattr(connector, "execution_health"):
        try:
            execution_health = connector.execution_health()
        except Exception as exc:
            execution_health = {"error": f"{type(exc).__name__}: {exc}"}
    return {
        "ok": True,
        "venue": connector.name,
        "wallet": connector.wallet_address(),
        "ticks": ticks.health(),
        "execution": execution_health,
        "timestamp": time.time(),
    }


@app.get("/api/state")
def state(force: bool = False) -> dict[str, Any]:
    return _safe(lambda: execution_service.state(force=force))


@app.get("/api/status")
def legacy_status(pair: str | None = None) -> dict[str, Any]:
    selected = (pair or connector.feed_pairs[0]).upper().replace("/", "-")
    state_value = _safe(execution_service.state)
    price_value = _price_value(selected)
    position = next((item for item in state_value["positions"] if item["pair"] == selected), None)
    return {
        **state_value,
        "pair": selected,
        "price": price_value,
        "preset": {
            "collateral": DEFAULT_TICKET_USD,
            "leverage": DEFAULT_LEVERAGE,
            "notional": DEFAULT_TICKET_USD * DEFAULT_LEVERAGE,
            "marginMode": "isolated",
        },
        "position": position,
    }


@app.get("/api/price")
def price(pair: str | None = None) -> dict[str, Any]:
    selected = (pair or connector.feed_pairs[0]).upper().replace("/", "-")
    snapshot = ticks.snapshot(selected)
    latest = snapshot.get("latest")
    if latest:
        return {
            "pair": selected,
            "timestamp": int(float(latest["time"])),
            "price": {
                "mid": latest["mid"],
                "bid": latest["bid"],
                "ask": latest["ask"],
                "open": latest["open"],
            },
            "stale": snapshot["stale"],
        }
    return _safe(lambda: connector.price(selected))


@app.get("/api/tape")
def tape(pair: str, since: int = Query(default=0, ge=0)) -> dict[str, Any]:
    snapshot = ticks.snapshot(pair, since)
    snapshot["ticks"] = _thin_ticks(snapshot.get("ticks", []), max_points=90 if since == 0 else 40)
    return snapshot


@app.get("/api/chart")
def chart(pair: str | None = None, minutes: int = Query(default=20, ge=5, le=180)) -> dict[str, Any]:
    selected = (pair or connector.feed_pairs[0]).upper().replace("/", "-")
    historical = _safe(lambda: connector.chart(selected, minutes=minutes))
    live_ticks = ticks.recent(selected, seconds=min(minutes * 60, 180))
    live_ticks = _thin_ticks(live_ticks, max_points=180)
    live_points = [float(item["mid"]) for item in live_ticks if float(item.get("mid") or 0) > 0]
    points = live_points if len(live_points) >= 8 else historical.get("points", [])
    return {**historical, "points": points, "ticks": live_ticks}


@app.get("/api/markets")
def markets() -> dict[str, Any]:
    return _safe(market_service.snapshot)


@app.get("/api/positions")
def positions() -> dict[str, Any]:
    return _safe(execution_service.state)


@app.get("/api/history")
def history(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    return {"trades": execution_service.history(limit)}


@app.get("/api/timings")
def timings(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    return {"executions": execution_service.timings(limit)}


@app.get("/api/executions/{execution_id}")
def execution(execution_id: str) -> dict[str, Any]:
    return _safe(lambda: execution_service.execution(execution_id))


@app.get("/api/executions/{execution_id}/timeline")
def execution_timeline(execution_id: str) -> dict[str, Any]:
    return _safe(lambda: execution_service.execution_timing(execution_id))


@app.post("/api/trade/quote")
def quote(body: QuoteRequest, x_tick_token: str | None = Header(default=None)) -> dict[str, Any]:
    _authorize(x_tick_token)
    return _safe(
        lambda: execution_service.quote(
            body.pair,
            body.side.lower(),
            Decimal(str(body.ticketUsd)),
            Decimal(str(body.leverage)),
        )
    )


@app.post("/api/trade/open", status_code=status.HTTP_202_ACCEPTED)
def open_trade(body: OpenRequest, x_tick_token: str | None = Header(default=None)) -> dict[str, Any]:
    _authorize(x_tick_token)
    return _safe(lambda: execution_service.open(body.quoteId, body.idempotencyKey))


@app.post("/api/trade/close", status_code=status.HTTP_202_ACCEPTED)
def close_trade(body: CloseRequest, x_tick_token: str | None = Header(default=None)) -> dict[str, Any]:
    _authorize(x_tick_token)
    return _safe(lambda: execution_service.close(body.pair, body.idempotencyKey))


@app.post("/api/approve")
def approve(body: ApproveRequest | None = None, x_tick_token: str | None = Header(default=None)) -> dict[str, Any]:
    _authorize(x_tick_token)
    amount = Decimal(str(body.amount)) if body and body.amount is not None else None
    return _safe(lambda: connector.approve(amount))


@app.post("/api/open", status_code=status.HTTP_202_ACCEPTED, deprecated=True)
def legacy_open(body: LegacyOpenRequest, x_tick_token: str | None = Header(default=None)) -> dict[str, Any]:
    _authorize(x_tick_token)
    pair = body.pair or connector.feed_pairs[0]
    leverage = Decimal(str(body.leverage or DEFAULT_LEVERAGE))

    def submit() -> dict[str, Any]:
        quote_value = execution_service.quote(pair, body.side.lower(), Decimal(str(DEFAULT_TICKET_USD)), leverage)
        return execution_service.open(quote_value["quoteId"], f"legacy-open-{uuid.uuid4().hex}")

    return _safe(submit)


@app.post("/api/close", status_code=status.HTTP_202_ACCEPTED, deprecated=True)
def legacy_close(body: LegacyCloseRequest | None = None, x_tick_token: str | None = Header(default=None)) -> dict[str, Any]:
    _authorize(x_tick_token)
    pair = body.pair if body and body.pair else connector.feed_pairs[0]
    return _safe(lambda: execution_service.close(pair, f"legacy-close-{uuid.uuid4().hex}"))


def _price_value(pair: str) -> dict[str, Any]:
    latest = ticks.snapshot(pair).get("latest")
    if latest:
        return {
            "mid": latest["mid"],
            "bid": latest["bid"],
            "ask": latest["ask"],
            "open": latest["open"],
        }
    return _safe(lambda: connector.price(pair))["price"]


def _thin_ticks(items: list[dict[str, Any]], max_points: int) -> list[dict[str, Any]]:
    if len(items) <= max_points:
        return items
    if max_points <= 1:
        return items[-1:]
    step = (len(items) - 1) / (max_points - 1)
    return [items[round(index * step)] for index in range(max_points)]


def _authorize(token: str | None) -> None:
    if token != LOCAL_API_TOKEN:
        raise HTTPException(status_code=401, detail="invalid local API token")


def _safe(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except (ConnectorError, ExecutionError) as exc:
        LOGGER.warning("request rejected: %s", exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("unexpected request failure")
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
