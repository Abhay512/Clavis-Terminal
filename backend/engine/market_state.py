"""In-memory live state for every monitored instrument."""
from __future__ import annotations

import math
from collections import deque
from datetime import datetime

import config
from engine import bar_builder
from engine.bar_builder import Bar, WorkingBar
from universe import Instrument, Universe


class InstrumentState:
    __slots__ = ("inst", "bars", "working", "last_price", "last_oi",
                 "cum_volume", "baseline_mean", "baseline_std",
                 "last_signal_minute", "bars_seen", "day_open",
                 "prev_close", "exch_open", "sess_high", "sess_low")

    def __init__(self, inst: Instrument):
        self.inst = inst
        self.bars: deque[Bar] = deque(maxlen=config.BAR_RING_SIZE)
        self.working: WorkingBar | None = None
        self.last_price: float = 0.0
        self.last_oi: int = 0
        self.cum_volume: int = 0
        self.baseline_mean: float = 0.0
        self.baseline_std: float = 0.0
        self.last_signal_minute: datetime | None = None
        self.bars_seen: int = 0    # counts real (non-carry) bars today
        self.day_open: float = 0.0
        self.prev_close: float = 0.0
        self.exch_open: float = 0.0
        self.sess_high: float = 0.0
        self.sess_low: float = 0.0

    def set_day_refs(self, exch_open: float, prev_close: float) -> None:
        if exch_open > 0 and self.exch_open <= 0:
            self.exch_open = exch_open
        if prev_close > 0 and self.prev_close <= 0:
            self.prev_close = prev_close

    def day_pct(self) -> float:
        """% move on the day. Base = previous close (what Kite/terminals show); falls back to exchange."""
        base = self.prev_close or self.exch_open or self.day_open
        if base <= 0 or self.last_price <= 0:
            return 0.0
        return (self.last_price - base) / base * 100.0

    # ------------------------------------------------------------ ticks ----
    def on_tick(self, price: float, cum_volume: int, oi: int,
                minute: datetime) -> bool:
        """Update state with one tick. Returns True if OI changed
        (the trigger for the instant spike check)."""
        oi_changed = oi > 0 and oi != self.last_oi
        if self.day_open <= 0:
            self.day_open = price
        if price > self.sess_high:
            self.sess_high = price
        if price < self.sess_low or self.sess_low <= 0:
            self.sess_low = price
        if self.working is None:
            self.working = bar_builder.open_bar(minute, price,
                                                self.cum_volume, oi or self.last_oi)
        elif self.working.minute != minute:
            self.close_working()
            self.working = bar_builder.open_bar(minute, price,
                                                self.cum_volume, oi or self.last_oi)
        bar_builder.update_bar(self.working, price, cum_volume, oi)
        self.last_price = price
        if cum_volume > self.cum_volume:
            self.cum_volume = cum_volume
        if oi > 0:
            self.last_oi = oi
        return oi_changed

    # -------------------------------------------------------- bar close ----
    def close_working(self) -> Bar | None:
        if self.working is None:
            return None
        prev_oi = self.bars[-1].oi if self.bars else None
        bar = bar_builder.close_bar(self.working, prev_oi)
        self.working = None
        self.bars.append(bar)
        self.bars_seen += 1
        self._refresh_baseline()
        return bar

    def append_carry(self, minute: datetime) -> Bar | None:
        if not self.bars:
            return None
        bar = bar_builder.carry_bar(minute, self.bars[-1])
        self.bars.append(bar)
        return bar

    def _refresh_baseline(self) -> None:
        """Cache mean/std of recent 1-min OI deltas for O(1) z-scores. Feed-gap catch-up bars are."""
        n = min(len(self.bars), config.BASELINE_BARS)
        if n < config.BASELINE_MIN_BARS:
            self.baseline_std = 0.0
            return
        deltas = [self.bars[-i].oi_delta for i in range(1, n + 1)
                  if not self.bars[-i].artifact]
        n = len(deltas)
        if n < config.BASELINE_MIN_BARS:
            self.baseline_std = 0.0
            return
        mean = sum(deltas) / n
        var = sum((d - mean) ** 2 for d in deltas) / n
        self.baseline_mean = mean
        self.baseline_std = math.sqrt(var)


class MarketState:
    def __init__(self, universe: Universe):
        self.universe = universe
        self.by_token: dict[int, InstrumentState] = {
            inst.token: InstrumentState(inst) for inst in universe.instruments
        }
        self.futures_by_underlying: dict[str, InstrumentState] = {
            s.inst.underlying: s for s in self.by_token.values()
            if s.inst.kind == "FUT"
        }
        self.options_by_underlying: dict[str, list[InstrumentState]] = {}
        for s in self.by_token.values():
            if s.inst.kind in ("CE", "PE"):
                self.options_by_underlying.setdefault(
                    s.inst.underlying, []).append(s)

    def close_minute(self, minute: datetime) -> list[tuple[InstrumentState, Bar]]:
        """Close all working bars for `minute`; carry-forward silent
        instruments. Returns (state, bar) pairs for storage/analytics."""
        closed: list[tuple[InstrumentState, Bar]] = []
        for state in self.by_token.values():
            if state.working is not None and state.working.minute <= minute:
                bar = state.close_working()
            elif state.bars and state.bars[-1].minute == minute:
                bar = state.bars[-1]
            else:
                bar = state.append_carry(minute)
            if bar is not None:
                closed.append((state, bar))
        return closed

    def underlying_price(self, underlying: str) -> float:
        fut = self.futures_by_underlying.get(underlying)
        return fut.last_price if fut else 0.0
