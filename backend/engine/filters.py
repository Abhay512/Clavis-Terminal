"""Shared protection filters: straddle pin, OI wall runway, VWAP, RVOL."""
from __future__ import annotations

import config
from engine import classifier, oi_engine
from engine.market_state import InstrumentState, MarketState
from engine.spike_detector import SIGNAL_WINDOW

Chain = dict[float, dict[str, InstrumentState]]


def build_chains(market: MarketState) -> dict[str, Chain]:
    """underlying -> strike -> {kind: state}, for pin / wall tracing."""
    chains: dict[str, Chain] = {}
    for ul, states in market.options_by_underlying.items():
        chain: Chain = {}
        for s in states:
            chain.setdefault(s.inst.strike, {})[s.inst.kind] = s
        chains[ul] = chain
    return chains


def straddle_pinned(chain: Chain, spot: float) -> bool:
    atm = min(chain, key=lambda k: abs(k - spot))
    sides = {}
    for kind, state in chain[atm].items():
        m = oi_engine.compute(state, SIGNAL_WINDOW, intrabar=False)
        if m is not None:
            sides[kind] = classifier.classify(m.oi_delta, m.price_pct)
    return (sides.get("CE") == classifier.SHORT_BUILDUP and
            sides.get("PE") == classifier.SHORT_BUILDUP)


def wall_runway(chain: Chain, spot: float, direction: str
                ) -> tuple[float, str]:
    """(runway %, wall label); (99, "") when no wall in the way."""
    strikes = sorted(chain, key=lambda k: abs(k - spot))
    span = strikes[:2 * config.EARLY_STRIKES_SPAN]
    kind = "CE" if direction == "BUY" else "PE"
    wall_strike, wall_oi = 0.0, 0
    for strike in span:
        if direction == "BUY" and strike <= spot:
            continue
        if direction == "SELL" and strike >= spot:
            continue
        state = chain[strike].get(kind)
        if state is None or not state.bars:
            continue
        oi = state.bars[-1].oi
        if oi > wall_oi:
            wall_strike, wall_oi = strike, oi
    if wall_oi <= 0:
        return 99.0, ""
    return abs(wall_strike - spot) / spot * 100.0, f"{wall_strike:g}{kind}"


def vwap_pct(fut: InstrumentState) -> float:
    pv = vol = 0.0
    for b in fut.bars:
        if b.volume > 0:
            pv += b.close * b.volume
            vol += b.volume
    if vol <= 0 or fut.last_price <= 0:
        return 0.0
    vwap = pv / vol
    return (fut.last_price - vwap) / vwap * 100.0


def extreme_distance_pct(fut: InstrumentState, direction: str) -> float:
    """Percent distance of the live price from the session extreme in `direction`."""
    px = fut.last_price
    if px <= 0:
        return 99.0
    hi, lo = fut.sess_high, fut.sess_low
    if hi <= 0 or lo <= 0:
        if not fut.bars:
            return 99.0
        hi = max(b.high for b in fut.bars)
        lo = min(b.low for b in fut.bars)
    if direction == "BUY":
        return max(0.0, (hi - px) / px * 100.0)
    return max(0.0, (px - lo) / px * 100.0)


def rvol(fut: InstrumentState) -> float:
    bars = fut.bars
    n = len(bars)
    if n < 10:
        return 0.0
    recent = sum(bars[-i].volume for i in range(1, 6))
    avg5 = sum(b.volume for b in bars) / n * 5
    return recent / avg5 if avg5 > 0 else 0.0


def oneway_ratio(fut: InstrumentState, direction: str,
                 lookback: int | None = None) -> float:
    bars = list(fut.bars)[-((lookback or config.MOM_ONEWAY_BARS) + 1):]
    ups = downs = 0
    for prev, cur in zip(bars, bars[1:], strict=False):
        if cur.close > prev.close:
            ups += 1
        elif cur.close < prev.close:
            downs += 1
    decided = ups + downs
    if decided < 5:
        return 0.0
    return (ups if direction == "BUY" else downs) / decided
