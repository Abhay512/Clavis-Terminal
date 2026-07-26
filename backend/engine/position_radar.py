"""Per-stock view of where size is being built in the option chain.

Reference implementation. The production breakout arming rule - the flow
acceleration test, its agreement conditions and its re-arm behaviour - is not
published; this version uses a plain range break so the board still marks the
minute a loaded position starts to move.
"""
from __future__ import annotations

import logging
import math
import statistics
from collections import deque
from dataclasses import dataclass
from datetime import datetime

import config
from engine.market_state import MarketState
from engine.ranking import StockRank, flows_4way

log = logging.getLogger("position")


@dataclass(slots=True)
class PositionBuild:
    ts: datetime
    underlying: str
    direction: str            # BUY | SELL
    phase: str                # LOADED | BUILDING | MOVING
    score: float              # 0-100
    cum_net_cr: float
    cum_total_cr: float
    dominance: float          # one-sidedness of the day's money (0-1)
    persistence: float        # share of minutes agreeing with the cumulative
    fut_price: float
    price_pct_day: float
    first_seen: datetime
    breakout_ts: datetime | None
    monitored_min: int
    ce_wall: str              # biggest call OI build today
    pe_wall: str              # biggest put OI build today
    note: str


class _Track:
    __slots__ = ("cum_net", "cum_tot", "decided", "with_cum", "absnet",
                 "first_seen", "breakout_ts", "breakout_dir", "nets")

    def __init__(self):
        self.cum_net = 0.0
        self.cum_tot = 0.0
        self.decided = 0
        self.with_cum = 0
        self.absnet: list[float] = []
        self.first_seen: datetime | None = None
        self.breakout_ts: datetime | None = None
        self.breakout_dir = ""
        self.nets: deque[float] = deque(maxlen=4)


class PositionRadar:
    def __init__(self, market: MarketState):
        self.market = market
        self._tracks: dict[str, _Track] = {}
        self._first_oi: dict[int, int] = {}

    # ------------------------------------------------------------ public ----
    def compute(self, rows: list[StockRank], ts: datetime
                ) -> list[PositionBuild]:
        scored: list[tuple[float, StockRank, _Track, float, float]] = []

        for r in rows:
            tr = self._tracks.setdefault(r.underlying, _Track())
            bull, bear = flows_4way(r)
            net, tot = bull - bear, bull + bear
            tr.cum_net += net / 5.0
            tr.cum_tot += tot / 5.0
            if net != 0:
                tr.decided += 1
                tr.absnet.append(abs(net))
                if net * tr.cum_net > 0:
                    tr.with_cum += 1
            tr.nets.append(net)

            mag = abs(tr.cum_net)
            if mag < config.POS_MIN_CUM_CR or tr.cum_tot <= 0:
                continue
            dom = mag / tr.cum_tot
            if dom < config.POS_MIN_DOM and mag < config.POS_BIG_CUM_CR:
                continue

            typical = max(config.POS_FLOW_FLOOR_CR,
                          statistics.median(tr.absnet) if tr.absnet else 0.0)
            build_x = mag / typical
            pers = tr.with_cum / tr.decided if tr.decided else 0.0
            mag_factor = min(1.0, math.log1p(build_x)
                             / math.log1p(config.POS_BUILD_FULL))
            scored.append((round(100.0 * dom * pers * mag_factor, 1),
                           r, tr, dom, pers))

        scored.sort(key=lambda c: c[0], reverse=True)
        out: list[PositionBuild] = []
        for score, r, tr, dom, pers in scored[:config.POS_TOP_N]:
            direction = "BUY" if tr.cum_net > 0 else "SELL"
            if tr.first_seen is None:
                tr.first_seen = ts
            self._check_breakout(r, tr, direction, ts)
            out.append(self._to_build(r, tr, direction, score, dom, pers, ts))
        return out

    # ------------------------------------------------------- breakout -------
    def _check_breakout(self, r: StockRank, tr: _Track, direction: str,
                        ts: datetime) -> None:
        """First close outside the trailing range, once the money agrees."""
        if tr.breakout_dir != direction:
            tr.breakout_ts = None
            tr.breakout_dir = direction
        if tr.breakout_ts is not None:
            return
        d = 1.0 if direction == "BUY" else -1.0
        if tr.cum_net * d < config.POS_BURST_CUM_CR:
            return
        fut = self.market.futures_by_underlying.get(r.underlying)
        if fut is None or len(fut.bars) < config.POS_BREAK_LOOKBACK + 1:
            return
        closes = [b.close for b in fut.bars]
        window = closes[-(config.POS_BREAK_LOOKBACK + 1):-1]
        px = closes[-1]
        if px > max(window) if d > 0 else px < min(window):
            tr.breakout_ts = ts
            log.info("POSITION BREAKOUT %s %s @ %.1f (cum Rs %.0fcr)",
                     direction, r.underlying, px, tr.cum_net)

    # ------------------------------------------------------------ output ----
    def _to_build(self, r: StockRank, tr: _Track, direction: str, score: float,
                  dom: float, pers: float, ts: datetime) -> PositionBuild:
        d = 1.0 if direction == "BUY" else -1.0
        day = r.price_pct_day
        if d * day >= config.POS_MOVING_MIN_DAY:
            phase = "MOVING"
        elif abs(day) <= config.POS_LOADED_MAX_DAY:
            phase = "LOADED"
        else:
            phase = "BUILDING"

        fut = self.market.futures_by_underlying.get(r.underlying)
        ce_wall, pe_wall = self._walls(r.underlying)
        note = ""
        if phase == "LOADED":
            note = "position built, price still quiet"
        elif tr.breakout_ts is not None:
            note = f"breakout {tr.breakout_ts:%H:%M}"

        return PositionBuild(
            ts=ts, underlying=r.underlying, direction=direction, phase=phase,
            score=round(score, 1), cum_net_cr=round(tr.cum_net, 1),
            cum_total_cr=round(tr.cum_tot, 1), dominance=round(dom, 2),
            persistence=round(pers, 2), fut_price=r.fut_price,
            price_pct_day=day, first_seen=tr.first_seen or ts,
            breakout_ts=tr.breakout_ts,
            monitored_min=fut.bars_seen if fut is not None else 0,
            ce_wall=ce_wall, pe_wall=pe_wall, note=note,
        )

    def _walls(self, underlying: str) -> tuple[str, str]:
        """Biggest call and put OI builds today across the chain."""
        best = {"CE": (0, ""), "PE": (0, "")}
        for state in self.market.options_by_underlying.get(underlying, ()):
            if not state.bars:
                continue
            first = self._first_oi.setdefault(state.inst.token,
                                              state.bars[0].oi)
            delta = state.bars[-1].oi - first
            kind = state.inst.kind
            if delta > best[kind][0]:
                best[kind] = (delta,
                              f"{state.inst.strike:g}{kind} "
                              f"+{delta / 1000:.0f}k")
        return best["CE"][1], best["PE"][1]
