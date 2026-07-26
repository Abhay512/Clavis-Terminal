"""Rolling OI-change metrics and z-scores over configurable windows."""
from __future__ import annotations

from dataclasses import dataclass

import config
from engine.market_state import InstrumentState


@dataclass(slots=True)
class WindowMetrics:
    window: int              # minutes
    oi_now: int
    oi_then: int
    oi_delta: int
    oi_pct: float            # % change vs window start
    price_now: float
    price_then: float
    price_pct: float
    volume: int              # traded volume within the window
    zscore: float            # of the 1-min delta vs trailing baseline


def zscore_1m(state: InstrumentState, delta_1m: float) -> float:
    std = state.baseline_std
    if std <= 0.0:
        return config.ZSCORE_CAP if abs(delta_1m) > 0 else 0.0
    z = (delta_1m - state.baseline_mean) / std
    return max(-config.ZSCORE_CAP, min(config.ZSCORE_CAP, z))


def compute(state: InstrumentState, window: int,
            intrabar: bool = False) -> WindowMetrics | None:
    """Metrics for `window` minutes ending now.

    intrabar=True uses the live working values as the endpoint (tick path);
    otherwise the endpoint is the last closed bar.
    """
    bars = state.bars
    if intrabar:
        if not bars:
            return None
        oi_now = state.last_oi
        price_now = state.last_price
        # window start = close of the bar `window` bars ago
        idx = min(window, len(bars))
        ref = bars[-idx]
        vol = sum(bars[-i].volume for i in range(1, idx))
        if state.working is not None:
            vol += max(0, state.working.vol_end - state.working.vol_start)
        delta_1m = oi_now - bars[-1].oi
    else:
        if len(bars) < 2:
            return None
        oi_now = bars[-1].oi
        price_now = bars[-1].close
        idx = min(window + 1, len(bars))
        ref = bars[-idx]
        vol = sum(bars[-i].volume for i in range(1, idx))
        delta_1m = bars[-1].oi_delta
    if any(bars[-i].artifact for i in range(1, idx + 1)):
        return None

    oi_then = ref.oi
    price_then = ref.close
    oi_delta = oi_now - oi_then
    oi_pct = (oi_delta / oi_then * 100.0) if oi_then > 0 else 0.0
    price_pct = ((price_now - price_then) / price_then * 100.0) \
        if price_then > 0 else 0.0

    return WindowMetrics(
        window=window, oi_now=oi_now, oi_then=oi_then, oi_delta=oi_delta,
        oi_pct=oi_pct, price_now=price_now, price_then=price_then,
        price_pct=price_pct, volume=vol, zscore=zscore_1m(state, delta_1m),
    )
