"""Turn window metrics into concrete spike signals."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import config
from engine import classifier, oi_engine
from engine.market_state import InstrumentState

log = logging.getLogger("spike")

SIGNAL_WINDOW = 5  # minutes - primary detection window


@dataclass(slots=True)
class Signal:
    ts: datetime
    token: int
    tradingsymbol: str
    underlying: str
    kind: str                 # FUT | CE | PE
    strike: float
    expiry: str
    window: int
    oi_now: int
    oi_delta: int
    oi_pct: float
    zscore: float
    price: float
    price_pct: float
    volume: int
    classification: str       # LONG_BUILDUP / SHORT_BUILDUP / ...
    side: str                 # BUY_SIDE / SELL_SIDE / "" for futures
    underlying_price: float
    notional_cr: float        # rupee notional of the OI change, in crores
    score: float              # composite 0-100
    intrabar: bool
    monitored_min: int = 0    # minutes this contract has been watched today


def _score(m: oi_engine.WindowMetrics, pct_threshold: float) -> float:
    z_part = min(1.0, m.zscore / (2.0 * config.SPIKE_ZSCORE_MIN)) \
        * config.SCORE_W_ZSCORE
    pct_part = min(1.0, abs(m.oi_pct) / (2.0 * pct_threshold)) \
        * config.SCORE_W_OI_PCT
    vol_part = (min(1.0, m.volume / abs(m.oi_delta))
                if m.oi_delta else 0.0) * config.SCORE_W_VOLUME
    return round(min(100.0, z_part + pct_part + vol_part), 1)


class SpikeDetector:
    def __init__(self, market_state):
        self.market = market_state

    def check(self, state: InstrumentState, ts: datetime,
              intrabar: bool = False) -> Signal | None:
        if state.bars_seen < config.WARMUP_BARS:
            return None
        if (state.last_signal_minute is not None and
                ts - state.last_signal_minute <
                timedelta(minutes=config.SPIKE_COOLDOWN_MIN)):
            return None

        m = oi_engine.compute(state, SIGNAL_WINDOW, intrabar=intrabar)
        if m is None:
            return None

        inst = state.inst
        is_fut = inst.kind == "FUT"
        pct_threshold = (config.SPIKE_OI_PCT_5M_FUT if is_fut
                         else config.SPIKE_OI_PCT_5M_OPT)

        if m.zscore < config.SPIKE_ZSCORE_MIN:
            return None
        if abs(m.oi_pct) < pct_threshold:
            return None
        if m.oi_now < config.SPIKE_MIN_OI_LOTS * inst.lot_size:
            return None
        if m.volume <= 0:
            return None

        cls = classifier.classify(m.oi_delta, m.price_pct)
        if cls == classifier.NEUTRAL:
            return None
        side = "" if is_fut else (classifier.option_side(cls) or "")

        und_price = self.market.underlying_price(inst.underlying) \
            or m.price_now
        notional_cr = abs(m.oi_delta) * und_price / 1e7

        state.last_signal_minute = ts
        return Signal(
            ts=ts, token=inst.token, tradingsymbol=inst.tradingsymbol,
            underlying=inst.underlying, kind=inst.kind, strike=inst.strike,
            expiry=inst.expiry.isoformat(), window=m.window,
            oi_now=m.oi_now, oi_delta=m.oi_delta, oi_pct=round(m.oi_pct, 2),
            zscore=round(m.zscore, 2), price=m.price_now,
            price_pct=round(m.price_pct, 2), volume=m.volume,
            classification=cls, side=side, underlying_price=und_price,
            notional_cr=round(notional_cr, 2),
            score=_score(m, pct_threshold), intrabar=intrabar,
            monitored_min=state.bars_seen,
        )
