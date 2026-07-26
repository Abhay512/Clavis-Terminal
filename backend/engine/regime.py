"""Day-regime meter: TREND / MIXED / CHOP, read live from the futures tape."""
from __future__ import annotations

import logging
from datetime import datetime, time

import config
from engine.market_state import MarketState

log = logging.getLogger("oi_screener")


class RegimeMeter:
    def __init__(self):
        self.regime = "MIXED"
        self.late_start = False
        self._start_marked = False
        # last computed diagnostics (for logging / display)
        self.ratio = 0.0
        self.active = 0
        self.n_gap = 0
        self.gap_hold = -1.0

    def mark_start(self, ts: datetime) -> None:
        """Mark the first minute processed; a late start caps the day at MIXED."""
        if not self._start_marked:
            self.late_start = ts.time() > config.REGIME_LATE_START
            self._start_marked = True
            if self.late_start:
                log.warning(
                    "REGIME: late start (first data %s > %s) - day capped at "
                    "MIXED, no full-size rides", ts.time(),
                    config.REGIME_LATE_START)

    def update(self, market: MarketState, ts: datetime) -> str:
        active = clean = faded = n_gap = held_n = held_ok = 0
        for fut in market.futures_by_underlying.values():
            o = fut.exch_open or fut.day_open
            px = fut.last_price
            if o <= 0 or px <= 0:
                continue
            up = px >= o
            ext = fut.sess_high if up else fut.sess_low
            if ext <= 0:
                continue
            denom = (ext - o) if up else (o - ext)
            peak = denom / o * 100.0
            if peak >= config.REGIME_ACTIVE_MOVE:
                active += 1
                retr = (((ext - px) if up else (px - ext)) / denom
                        if denom > 0 else 1.0)
                if retr <= config.REGIME_CLEAN_RETR:
                    clean += 1
                elif retr >= config.REGIME_FADE_RETR:
                    faded += 1
            # gap-conviction (opening read)
            pc = fut.prev_close
            if pc > 0:
                gap = (o - pc) / pc * 100.0
                if abs(gap) >= config.REGIME_GAP_MIN:
                    n_gap += 1
                    held = (((px - pc) / (o - pc)) if gap > 0
                            else ((pc - px) / (pc - o)))
                    held_n += 1
                    held_ok += held >= config.REGIME_GAP_KEEP
        ratio = clean / max(faded, 1)
        gh = (held_ok / held_n) if held_n else None

        if ts.time() >= time(10, 0) and active >= config.REGIME_MIN_ACTIVE:
            # main read: cleanliness breadth of the day's movers
            if ratio >= config.REGIME_TREND_RATIO:
                reg = "TREND"
            elif ratio <= config.REGIME_CHOP_RATIO:
                reg = "CHOP"
            else:
                reg = "MIXED"
        else:
            if (n_gap >= config.REGIME_GAP_CONVICTION and gh is not None
                    and gh >= config.REGIME_GAPHOLD_TREND):
                reg = "TREND"
            elif (n_gap < config.REGIME_GAP_CONVICTION
                  or (gh is not None and gh <= config.REGIME_GAPHOLD_CHOP)):
                reg = "CHOP"
            else:
                reg = "MIXED"

        if self.late_start and reg == "TREND":
            reg = "MIXED"
        if reg != self.regime:
            log.info("REGIME %s -> %s (clean=%d faded=%d ratio=%.2f "
                     "active=%d gaps=%d hold=%s)", self.regime, reg,
                     clean, faded, ratio, active, n_gap,
                     f"{gh:.2f}" if gh is not None else "n/a")
        self.regime = reg
        self.ratio = ratio
        self.active = active
        self.n_gap = n_gap
        self.gap_hold = gh if gh is not None else -1.0
        return reg
