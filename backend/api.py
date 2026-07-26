"""FastAPI REST + WebSocket bridge between the engine and the dashboard."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import config
from engine.big_player_radar import BigPlayerSignal
from engine.oi_multiple import OIMultipleRow
from engine.oneway_momentum import OneWayMover
from engine.position_radar import PositionBuild
from engine.sector_leaders import SectorLeader
from engine.spike_detector import Signal
from engine.ranking import StockRank
from sinks.signal_bus import SignalBus
from sinks.storage import SignalStore

log = logging.getLogger("api")

app = FastAPI(title="OI Screener API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------- shared state
# These are set by main.py before uvicorn starts.
_bus: SignalBus | None = None
_store: SignalStore | None = None
_universe_size: int = 0

_signal_queue: asyncio.Queue = asyncio.Queue(maxsize=5000)
_ranking_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
_position_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
_oneway_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
_radar_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
_oimult_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
_sector_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
_clients: set[WebSocket] = set()
_latest_rankings: list[dict] = []
_latest_position: list[dict] = []
_latest_oneway: list[dict] = []
_latest_radar: list[dict] = []
_latest_oimult: list[dict] = []
_latest_sector: list[dict] = []
_status: dict[str, Any] = {
    "market_open": False,
    "instruments": 0,
    "signals_today": 0,
    "connected_at": None,
    "feed_down": False,
    "feed_note": "",
}


def init(bus: SignalBus, store: SignalStore, universe_size: int) -> None:
    """Called from main.py to inject live components."""
    global _bus, _store, _universe_size
    _bus = bus
    _store = store
    _universe_size = universe_size
    _status["instruments"] = universe_size
    try:
        _status["signals_today"] = len(store.signals_for_day(date.today()))
    except Exception:
        log.warning("Could not seed signals_today from store", exc_info=True)

    bus.on_signal(_sync_signal)
    bus.on_ranking(_sync_ranking)
    bus.on_position(_sync_position)
    bus.on_oneway(_sync_oneway)
    bus.on_radar(_sync_radar)
    bus.on_oimult(_sync_oimult)
    bus.on_sector(_sync_sector)
    bus.on_feed(_sync_feed)
    log.info("API bridge wired to signal bus.")


def _sig_to_dict(s: Signal) -> dict:
    return {
        "ts": s.ts.isoformat(), "token": s.token,
        "tradingsymbol": s.tradingsymbol, "underlying": s.underlying,
        "kind": s.kind, "strike": s.strike, "expiry": s.expiry,
        "oi_now": s.oi_now, "oi_delta": s.oi_delta, "oi_pct": s.oi_pct,
        "zscore": s.zscore, "price": s.price, "price_pct": s.price_pct,
        "volume": s.volume, "classification": s.classification,
        "side": s.side, "underlying_price": s.underlying_price,
        "notional_cr": s.notional_cr, "score": s.score,
        "intrabar": s.intrabar, "monitored_min": s.monitored_min,
    }


def _rank_to_dict(r: StockRank) -> dict:
    return {
        "ts": r.ts.isoformat(), "underlying": r.underlying,
        "fut_price": r.fut_price,
        "price_pct_day": r.price_pct_day,
        "fut_classification": r.fut_classification,
        "buy_units": r.buy_units, "sell_units": r.sell_units,
        "buy_notional_cr": r.buy_notional_cr,
        "sell_notional_cr": r.sell_notional_cr,
        "ce_buy_cr": r.ce_buy_cr, "pe_buy_cr": r.pe_buy_cr,
        "ce_write_cr": r.ce_write_cr, "pe_write_cr": r.pe_write_cr,
        "ce_cover_cr": r.ce_cover_cr, "pe_cover_cr": r.pe_cover_cr,
        "ce_unwind_cr": r.ce_unwind_cr, "pe_unwind_cr": r.pe_unwind_cr,
        "top_buy_strike": r.top_buy_strike,
        "top_sell_strike": r.top_sell_strike,
        "top_ce_buy_strike": r.top_ce_buy_strike,
        "top_pe_buy_strike": r.top_pe_buy_strike,
    }


def _radar_to_dict(s: BigPlayerSignal) -> dict:
    return {
        "ts": s.ts.isoformat(), "underlying": s.underlying,
        "direction": s.direction, "strength": s.strength,
        "near_dom": s.near_dom, "net_cr": s.net_cr, "fut_price": s.fut_price,
        "price_pct_day": s.price_pct_day, "ce_strike": s.ce_strike,
        "pe_strike": s.pe_strike, "n_strikes": s.n_strikes,
        "first_seen": s.first_seen.isoformat(),
        "monitored_min": s.monitored_min, "note": s.note,
    }


def _oneway_to_dict(m: OneWayMover) -> dict:
    return {
        "ts": m.ts.isoformat(), "underlying": m.underlying,
        "direction": m.direction, "status": m.status, "score": m.score,
        "entry_ts": m.entry_ts.isoformat(), "entry_price": m.entry_price,
        "last_price": m.last_price, "pnl_pct": m.pnl_pct,
        "price_pct_day": m.price_pct_day, "build_x": m.build_x,
        "dominance": m.dominance, "clean_flow": m.clean_flow,
        "retrace_pct": m.retrace_pct, "two_sided": m.two_sided,
        "cum_net_cr": m.cum_net_cr, "monitored_min": m.monitored_min,
        "contract": m.contract, "note": m.note, "reasons": m.reasons,
        "kind": m.kind,
        "prime_window": m.prime_window,
        "conviction": m.conviction,
        "conv_ts": m.conv_ts.isoformat() if m.conv_ts else None,
        "stalling": m.stalling,
        "stop_px": m.stop_px,
        "fuel_forced_cr": m.fuel_forced_cr,
        "fuel_spec_cr": m.fuel_spec_cr,
        "forced_share": m.forced_share,
        "regime": m.regime,
        "size": m.size,
        "promo_pct": m.promo_pct,
        "exit_risk": m.exit_risk,
    }


def _oimult_to_dict(r: OIMultipleRow) -> dict:
    return {
        "ts": r.ts.isoformat(), "underlying": r.underlying,
        "running_max": r.running_max, "contract": r.contract,
        "base_oi": r.base_oi, "peak_oi": r.peak_oi,
        "t_max": r.t_max.isoformat(),
        "first_2x": r.first_2x.isoformat() if r.first_2x else None,
        "strikes_2x": r.strikes_2x, "direction": r.direction,
        "dominance": r.dominance, "bull_cr": r.bull_cr,
        "bear_cr": r.bear_cr, "top_writer": r.top_writer,
        "fresh": r.fresh, "fut_price": r.fut_price,
        "price_pct_day": r.price_pct_day,
        "monitored_min": r.monitored_min,
        "counter_tape": r.counter_tape,
    }


def _sector_to_dict(r: SectorLeader) -> dict:
    return {
        "ts": r.ts.isoformat(), "sector": r.sector,
        "sector_strength": r.sector_strength, "sector_rank": r.sector_rank,
        "underlying": r.underlying, "direction": r.direction,
        "move_pct": r.move_pct, "rank_in_sector": r.rank_in_sector,
        "fut_price": r.fut_price,
        "breakout_ts": r.breakout_ts.isoformat() if r.breakout_ts else None,
        "locked": r.locked,
    }


def _position_to_dict(b: PositionBuild) -> dict:
    return {
        "ts": b.ts.isoformat(), "underlying": b.underlying,
        "direction": b.direction, "phase": b.phase, "score": b.score,
        "cum_net_cr": b.cum_net_cr, "cum_total_cr": b.cum_total_cr,
        "dominance": b.dominance, "persistence": b.persistence,
        "fut_price": b.fut_price, "price_pct_day": b.price_pct_day,
        "first_seen": b.first_seen.isoformat(),
        "breakout_ts": b.breakout_ts.isoformat() if b.breakout_ts else None,
        "monitored_min": b.monitored_min,
        "ce_wall": b.ce_wall, "pe_wall": b.pe_wall, "note": b.note,
    }


# Sync callbacks (called from screener thread)
def _sync_signal(s: Signal) -> None:
    _status["signals_today"] = _status.get("signals_today", 0) + 1
    try:
        _signal_queue.put_nowait({"type": "signal", "data": _sig_to_dict(s)})
    except asyncio.QueueFull:
        pass


def _sync_ranking(rows: list[StockRank]) -> None:
    global _latest_rankings
    data = [_rank_to_dict(r) for r in rows]
    _latest_rankings = data
    try:
        _ranking_queue.put_nowait({"type": "ranking", "data": data})
    except asyncio.QueueFull:
        pass


def _sync_position(builds: list[PositionBuild]) -> None:
    global _latest_position
    data = [_position_to_dict(b) for b in builds]
    _latest_position = data
    try:
        _position_queue.put_nowait({"type": "position", "data": data})
    except asyncio.QueueFull:
        pass


def _sync_oneway(movers: list[OneWayMover]) -> None:
    global _latest_oneway
    data = [_oneway_to_dict(m) for m in movers]
    _latest_oneway = [d for d in data if d["status"] != "EXIT"]
    try:
        _oneway_queue.put_nowait({"type": "oneway", "data": data})
    except asyncio.QueueFull:
        pass


def _sync_radar(sigs: list[BigPlayerSignal]) -> None:
    global _latest_radar
    data = [_radar_to_dict(s) for s in sigs]
    _latest_radar = data
    try:
        _radar_queue.put_nowait({"type": "radar", "data": data})
    except asyncio.QueueFull:
        pass


def _sync_oimult(rows: list[OIMultipleRow]) -> None:
    global _latest_oimult
    data = [_oimult_to_dict(r) for r in rows]
    _latest_oimult = data
    try:
        _oimult_queue.put_nowait({"type": "oimult", "data": data})
    except asyncio.QueueFull:
        pass


def _sync_sector(rows: list[SectorLeader]) -> None:
    global _latest_sector
    data = [_sector_to_dict(r) for r in rows]
    _latest_sector = data
    try:
        _sector_queue.put_nowait({"type": "sector", "data": data})
    except asyncio.QueueFull:
        pass


def _sync_feed(status: dict) -> None:
    """Watchdog feed-health update, pushed to clients as a status frame."""
    _status.update(status)
    try:
        _radar_queue.put_nowait({"type": "status", "data": _status_payload()})
    except asyncio.QueueFull:
        pass


STATUS_PUSH_SECONDS = 30
SEND_TIMEOUT = 5.0


def _status_payload() -> dict:
    now = datetime.now()
    return {**_status,
            "market_open": config.MARKET_OPEN <= now.time() <= config.MARKET_CLOSE,
            "server_time": now.isoformat()}


async def _broadcast(raw: list[str]) -> None:
    """Send raw JSON frames to every client; drop clients that fail or stall."""
    dead: set[WebSocket] = set()
    for ws in list(_clients):
        for r in raw:
            try:
                await asyncio.wait_for(ws.send_text(r), timeout=SEND_TIMEOUT)
            except Exception:
                dead.add(ws)
                break
    if dead:
        _clients.difference_update(dead)
        for ws in dead:
            try:
                await asyncio.wait_for(ws.close(), timeout=1.0)
            except Exception:
                pass
        log.info("Dropped %d dead WS client(s) (%d remain)",
                 len(dead), len(_clients))


async def _status_loop() -> None:
    while True:
        await asyncio.sleep(STATUS_PUSH_SECONDS)
        try:
            if not _clients:
                continue
            raw = json.dumps({"type": "status", "data": _status_payload()})
            await _broadcast([raw])
        except Exception:
            log.exception("status loop error - continuing")


# Async fanout task - runs in the asyncio event loop
async def _fanout_loop() -> None:
    while True:
        try:
            msgs: list[dict] = []
            # Drain signals
            while not _signal_queue.empty():
                msgs.append(await _signal_queue.get())
            # Drain rankings
            while not _ranking_queue.empty():
                msgs.append(await _ranking_queue.get())
            # Drain position radar builds
            while not _position_queue.empty():
                msgs.append(await _position_queue.get())
            # Drain one-way movers
            while not _oneway_queue.empty():
                msgs.append(await _oneway_queue.get())
            # Drain big-player radar
            while not _radar_queue.empty():
                msgs.append(await _radar_queue.get())
            # Drain OI-multiple board
            while not _oimult_queue.empty():
                msgs.append(await _oimult_queue.get())
            # Drain sector-leader board
            while not _sector_queue.empty():
                msgs.append(await _sector_queue.get())
            if msgs and _clients:
                await _broadcast([json.dumps(m) for m in msgs])
        except Exception:
            log.exception("fanout loop error - continuing")
        await asyncio.sleep(0.05)   # 20 Hz fanout loop


@app.on_event("startup")
async def startup():
    asyncio.create_task(_fanout_loop())
    asyncio.create_task(_status_loop())
    log.info("Fanout + status loops started.")


# ------------------------------------------------------------ REST endpoints
@app.get("/api/status")
async def status():
    return _status_payload()


@app.get("/api/signals/today")
async def signals_today():
    if _store is None:
        return {"signals": [], "count": 0}
    rows = _store.signals_for_day(date.today())
    return {"signals": rows, "count": len(rows)}


@app.get("/api/rankings/latest")
async def rankings_latest():
    return {"rankings": _latest_rankings, "count": len(_latest_rankings)}


@app.get("/api/position/latest")
async def position_latest():
    return {"position": _latest_position, "count": len(_latest_position)}


@app.get("/api/oneway/latest")
async def oneway_latest():
    return {"oneway": _latest_oneway, "count": len(_latest_oneway)}


@app.get("/api/radar/latest")
async def radar_latest():
    return {"radar": _latest_radar, "count": len(_latest_radar)}


@app.get("/api/oimult/latest")
async def oimult_latest():
    return {"oimult": _latest_oimult, "count": len(_latest_oimult)}


@app.get("/api/sector/latest")
async def sector_latest():
    return {"sector": _latest_sector, "count": len(_latest_sector)}


# ------------------------------------------------------------ WebSocket
@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    await ws.accept()
    _clients.add(ws)
    log.info("WS client connected (%d total)", len(_clients))
    try:
        if _store is not None:
            today_sigs = _store.signals_for_day(date.today())
            await ws.send_text(json.dumps(
                {"type": "history", "data": today_sigs}))
        if _latest_rankings:
            await ws.send_text(json.dumps(
                {"type": "ranking", "data": _latest_rankings}))
        if _latest_position:
            await ws.send_text(json.dumps(
                {"type": "position", "data": _latest_position}))
        if _latest_radar:
            await ws.send_text(json.dumps(
                {"type": "radar", "data": _latest_radar}))
        if _latest_oneway:
            await ws.send_text(json.dumps(
                {"type": "oneway", "data": _latest_oneway}))
        if _latest_oimult:
            await ws.send_text(json.dumps(
                {"type": "oimult", "data": _latest_oimult}))
        if _latest_sector:
            await ws.send_text(json.dumps(
                {"type": "sector", "data": _latest_sector}))
        await ws.send_text(json.dumps(
            {"type": "status", "data": _status_payload()}))
        # Keep alive: read to detect disconnect
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        _clients.discard(ws)
        log.info("WS client disconnected (%d remain)", len(_clients))
    except Exception:
        _clients.discard(ws)
