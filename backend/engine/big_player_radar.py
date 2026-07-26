"""Near-spot strike scanner: OI build pace around the current price.

Reference implementation. The production scanner's strike weighting, pace
normalisation and strength curve are not published; this version measures the
same quantity in the most direct way and feeds the same downstream consumers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import config
from engine import classifier, oi_engine
from engine.market_state import InstrumentState, MarketState

log = logging.getLogger("radar")


@dataclass(slots=True)
class BigPlayerSignal:
    ts: datetime
    underlying: str
    direction: str            # BUY (bullish positioning) | SELL (bearish)
    strength: float           # 0-100
    near_dom: float           # one-sidedness of near-spot OI (0-1)
    net_cr: float             # signed near-spot net flow (Rs cr)
    fut_price: float
    price_pct_day: float
    ce_strike: str            # largest bullish contribution
    pe_strike: str            # largest bearish contribution
    n_strikes: int            # near-spot strikes that showed a build
    first_seen: datetime      # when this stock first appeared this direction
    monitored_min: int
    note: str = ""


class BigPlayerRadar:
    def __init__(self, market: MarketState):
        self.market = market
        self._chains: dict[str, dict[float, dict[str, InstrumentState]]] = {}
        for ul, states in market.options_by_underlying.items():
            chain: dict[float, dict[str, InstrumentState]] = {}
            for s in states:
                chain.setdefault(s.inst.strike, {})[s.inst.kind] = s
            self._chains[ul] = chain
        self._first: dict[str, tuple[str, datetime]] = {}
        # consumed by the one-way board and the cross-day baselines
        self.near_flows: dict[str, tuple[float, float]] = {}
        self.near_minute_hist: dict[str, list[float]] = {}

    def compute(self, ts: datetime) -> list[BigPlayerSignal]:
        out: list[BigPlayerSignal] = []
        for ul, chain in self._chains.items():
            sig = self._scan(ul, chain, ts)
            if sig is not None:
                out.append(sig)
        out.sort(key=lambda s: s.strength, reverse=True)
        top = out[:config.RADAR_TOP_N]
        live = {s.underlying for s in top}
        for ul in list(self._first):
            if ul not in live:
                del self._first[ul]
        return top

    def _scan(self, ul, chain, ts) -> BigPlayerSignal | None:
        fut = self.market.futures_by_underlying.get(ul)
        if fut is None or fut.last_price <= 0:
            return None
        spot = fut.last_price
        strikes = sorted(chain, key=lambda k: abs(k - spot))
        near = strikes[:2 * config.RADAR_ATM_STRIKES]
        to_cr = spot / 1e7

        bull = bear = 0.0
        n = 0
        best_bull = (0.0, "")
        best_bear = (0.0, "")

        for strike in near:
            for kind, state in chain[strike].items():
                m = oi_engine.compute(state, config.RADAR_WINDOW,
                                      intrabar=False)
                if m is None or m.oi_delta <= 0:
                    continue
                side = classifier.option_side(
                    classifier.classify(m.oi_delta, m.price_pct))
                if side is None:
                    continue
                cr = m.oi_delta * to_cr
                n += 1
                label = f"{strike:g}{kind} +{m.oi_delta // 1000}k"
                bullish = ((kind == "CE" and side == classifier.BUY_SIDE)
                           or (kind == "PE" and side == classifier.SELL_SIDE))
                if bullish:
                    bull += cr
                    if cr > best_bull[0]:
                        best_bull = (cr, label)
                else:
                    bear += cr
                    if cr > best_bear[0]:
                        best_bear = (cr, label)

        window = float(config.RADAR_WINDOW)
        self.near_flows[ul] = (bull / window, bear / window)
        self.near_minute_hist.setdefault(ul, []).append((bull + bear) / window)

        total = bull + bear
        net = bull - bear
        if total <= 0 or abs(net) < config.RADAR_MIN_FLOW_CR:
            return None
        near_dom = abs(net) / total
        if near_dom < config.RADAR_MIN_DOM:
            return None

        direction = "BUY" if net > 0 else "SELL"
        strength = min(100.0, abs(net) * near_dom * 4.0)

        prev = self._first.get(ul)
        if prev is None or prev[0] != direction:
            self._first[ul] = (direction, ts)

        return BigPlayerSignal(
            ts=ts, underlying=ul, direction=direction,
            strength=round(strength, 1), near_dom=round(near_dom, 2),
            net_cr=round(net, 1), fut_price=spot,
            price_pct_day=round(fut.day_pct(), 2),
            ce_strike=best_bull[1], pe_strike=best_bear[1], n_strikes=n,
            first_seen=self._first[ul][1], monitored_min=fut.bars_seen,
        )
