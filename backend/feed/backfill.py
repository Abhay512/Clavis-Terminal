"""Futures minute-bar backfill over a feed gap, via Kite historical REST."""
from __future__ import annotations

import logging
import queue
import threading
import time as time_mod
from datetime import datetime, timedelta

import config
from engine.bar_builder import Bar
from engine.market_state import InstrumentState, MarketState

log = logging.getLogger("backfill")


def fetch_futures_bars(kite, market: MarketState, start: datetime,
                       end: datetime) -> dict[int, list[Bar]]:
    """Minute bars for every futures instrument over [start, end], from the
    Kite historical API. Rate-limited (~3 req/s => ~1 min for all futures)."""
    out: dict[int, list[Bar]] = {}
    futs = list(market.futures_by_underlying.values())
    log.info("Backfilling %d futures for %s -> %s ...", len(futs),
             start.strftime("%H:%M"), end.strftime("%H:%M"))
    for st in futs:
        try:
            candles = kite.historical_data(st.inst.token, start, end,
                                           "minute", oi=True)
        except Exception as exc:
            log.warning("backfill %s failed: %s", st.inst.tradingsymbol, exc)
            time_mod.sleep(config.BACKFILL_RATE_SLEEP)
            continue
        bars: list[Bar] = []
        prev_oi: int | None = None
        for c in candles:
            minute = c["date"]
            if minute.tzinfo is not None:      # kite returns tz-aware IST
                minute = minute.replace(tzinfo=None)
            oi = int(c.get("oi") or 0)
            bars.append(Bar(
                minute=minute, open=float(c["open"]), high=float(c["high"]),
                low=float(c["low"]), close=float(c["close"]),
                volume=int(c["volume"]), oi=oi,
                oi_delta=(oi - prev_oi) if prev_oi is not None else 0))
            prev_oi = oi
        if bars:
            out[st.inst.token] = bars
        time_mod.sleep(config.BACKFILL_RATE_SLEEP)
    log.info("Backfill fetched bars for %d/%d futures.", len(out), len(futs))
    return out


def apply_backfill(state: InstrumentState, new_bars: list[Bar]) -> int:
    """Replace the gap's stale carry bars in `state.bars` with real ones and
    repair session extremes + the oi_delta chain. Consumer thread only."""
    if not new_bars:
        return 0
    by_min = {b.minute: b for b in new_bars}
    replaced = 0
    bars = state.bars
    for i in range(len(bars)):
        b = bars[i]
        nb = by_min.get(b.minute)
        if nb is not None and b.volume == 0:      # carry bar -> real bar
            bars[i] = nb
            replaced += 1
    if not replaced:
        return 0
    for nb in new_bars:                            # true price path seen now
        if nb.high > state.sess_high:
            state.sess_high = nb.high
        if state.sess_low <= 0 or nb.low < state.sess_low:
            state.sess_low = nb.low
    # the stale carried OI)
    prev_oi: int | None = None
    for i in range(len(bars)):
        if prev_oi is not None:
            bars[i].oi_delta = bars[i].oi - prev_oi
        prev_oi = bars[i].oi
    return replaced


def to_parquet_rows(market: MarketState,
                    fetched: dict[int, list[Bar]]) -> list[tuple]:
    """BAR_SCHEMA-ordered rows (backfilled=1) for BarWriter.add_backfill."""
    rows: list[tuple] = []
    for token, bars in fetched.items():
        st = market.by_token.get(token)
        if st is None:
            continue
        i = st.inst
        for b in bars:
            rows.append((b.minute, i.token, i.tradingsymbol, i.underlying,
                         i.kind, i.strike, b.open, b.high, b.low, b.close,
                         b.volume, b.oi, b.oi_delta, 1))
    return rows


class BackfillWorker:
    """Runs fetches off-thread; the consumer thread applies results between
    minutes via poll()."""

    def __init__(self, kite, market: MarketState):
        self._kite = kite
        self._market = market
        self._results: queue.Queue = queue.Queue()

    def request(self, start: datetime, end: datetime) -> None:
        if (end - start) < timedelta(minutes=config.BACKFILL_MIN_GAP_MIN):
            return
        threading.Thread(target=self._fetch, args=(start, end),
                         name="backfill", daemon=True).start()

    def _fetch(self, start: datetime, end: datetime) -> None:
        try:
            fetched = fetch_futures_bars(self._kite, self._market, start, end)
            if fetched:
                self._results.put(fetched)
        except Exception:
            log.exception("backfill fetch failed")

    def poll(self, bar_writer=None) -> int:
        """Apply any completed fetches. Returns bars replaced in memory."""
        replaced = 0
        while True:
            try:
                fetched = self._results.get_nowait()
            except queue.Empty:
                return replaced
            for token, bars in fetched.items():
                st = self._market.by_token.get(token)
                if st is not None:
                    replaced += apply_backfill(st, bars)
            if bar_writer is not None:
                bar_writer.add_backfill(to_parquet_rows(self._market, fetched))
            log.info("Backfill applied: %d in-memory bars repaired.", replaced)
