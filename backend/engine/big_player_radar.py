"""Near-spot strike scanner: OI build pace around the current price."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import config
from engine import classifier, filters, oi_engine
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
    ce_strike: str            # strongest bullish CE contribution "1200CE +45k"
    pe_strike: str            # strongest bullish/bearish PE contribution
    n_strikes: int            # near-spot strikes that showed a build
    first_seen: datetime      # when this stock first appeared this direction
    monitored_min: int
    note: str = ""


class BigPlayerRadar:
    def __init__(self, market: MarketState):
        self.market = market
        # underlying -> sorted strike -> {kind: state}
        self._chains: dict[str, dict[float, dict[str, InstrumentState]]] = {}
        for ul, states in market.options_by_underlying.items():
            chain: dict[float, dict[str, InstrumentState]] = {}
            for s in states:
                chain.setdefault(s.inst.strike, {})[s.inst.kind] = s
            self._chains[ul] = chain
        self._first: dict[str, tuple[str, datetime]] = {}   # ul -> (dir, ts)
        #                    - the One-Way loader flag's raw input
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
        for ul in list(self._first):        # forget stocks that dropped off
            if ul not in live:
                del self._first[ul]
        return top

    def _scan(self, ul, chain, ts) -> BigPlayerSignal | None:
        fut = self.market.futures_by_underlying.get(ul)
        if fut is None or fut.last_price <= 0:
            return None
        spot = fut.last_price
        strikes = sorted(chain, key=lambda k: abs(k - spot))
        near = strikes[:2 * config.RADAR_ATM_STRIKES]   # +/-N nearest
        to_cr = spot / 1e7
        bull = bear = 0.0
        n = 0
        top_ce = (0.0, "")    # (bullish cr, label)
        top_pe = (0.0, "")
        for strike in near:
            for kind, state in chain[strike].items():
                m = oi_engine.compute(state, config.RADAR_WINDOW, intrabar=False)
                if m is None or m.oi_delta <= 0:
                    continue
                cls = classifier.classify(m.oi_delta, m.price_pct)
                side = classifier.option_side(cls)
                if side is None:
                    continue
                cr = m.oi_delta * to_cr
                bullish = ((kind == "CE" and side == classifier.BUY_SIDE) or
                           (kind == "PE" and side == classifier.SELL_SIDE))
                n += 1
                label = f"{strike:g}{kind} +{m.oi_delta // 1000}k"
                if bullish:
                    bull += cr
                    if kind == "CE" and cr > top_ce[0]:
                        top_ce = (cr, label)
                    elif kind == "PE" and cr > top_pe[0]:
                        top_pe = (cr, label)
                else:
                    bear += cr
                    if kind == "CE" and cr > top_pe[0]:
                        top_pe = (cr, label)   # bearish CE write
                    elif kind == "PE" and cr > top_ce[0]:
                        top_ce = (cr, label)   # bearish PE buy

        w = float(config.RADAR_WINDOW)
        self.near_flows[ul] = (bull / w, bear / w)
        self.near_minute_hist.setdefault(ul, []).append((bull + bear) / w)

        total = bull + bear
        net = bull - bear
        if total <= 0 or abs(net) < config.RADAR_MIN_FLOW_CR:
            return None
        near_dom = abs(net) / total
        if near_dom < config.RADAR_MIN_DOM:
            return None
        direction = "BUY" if net > 0 else "SELL"
        strength = min(100.0, (abs(net) / 5.0) * 20.0 * near_dom)  # cr-scaled

        prev = self._first.get(ul)
        if prev is None or prev[0] != direction:
            self._first[ul] = (direction, ts)
        first_seen = self._first[ul][1]
        return BigPlayerSignal(
            ts=ts, underlying=ul, direction=direction,
            strength=round(strength, 1), near_dom=round(near_dom, 2),
            net_cr=round(net, 1), fut_price=spot,
            price_pct_day=round(fut.day_pct(), 2),
            ce_strike=top_ce[1], pe_strike=top_pe[1], n_strikes=n,
            first_seen=first_seen, monitored_min=fut.bars_seen,
        )
