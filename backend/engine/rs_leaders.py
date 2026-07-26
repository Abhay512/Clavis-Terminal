"""Shadow board: the day's top relative-strength leaders. Trades nothing."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import config
from engine.market_state import MarketState

log = logging.getLogger("oneway")


@dataclass(slots=True)
class RSLeader:
    ts: datetime
    underlying: str
    direction: str        # BUY (leading up) | SELL (leading down)
    rs: float             # directional strength vs the basket, %
    ret_pct: float        # stock return since open, %
    basket_pct: float     # market (equal-weight) return since open, %
    retrace: float        # realized pullback / move-so-far (0-1), lower = cleaner
    rank: int             # 1 = strongest
    fut_price: float
    locked: bool = False  # True on the daily decision snapshot


class RSLeaders:
    """Ranks stocks by directional relative strength; snapshots the top-N once a
    day at RSL_DECISION. Read-only - never opens or closes anything."""

    def __init__(self, market: MarketState):
        self.market = market
        self.locked_picks: list[RSLeader] = []
        self._locked = False

    def _basket(self) -> float:
        """Equal-weight mean return-since-open across all futures (%)."""
        tot = n = 0.0
        for fut in self.market.futures_by_underlying.values():
            o = fut.exch_open or fut.day_open
            if o > 0 and fut.last_price > 0:
                tot += (fut.last_price - o) / o * 100.0
                n += 1
        return tot / n if n else 0.0

    def compute(self, ts: datetime) -> list[RSLeader]:
        """Top-N leaders right now. Called every minute; cheap."""
        basket = self._basket()
        cands: list[RSLeader] = []
        for ul, fut in self.market.futures_by_underlying.items():
            o = fut.exch_open or fut.day_open
            px = fut.last_price
            if o <= 0 or px <= 0:
                continue
            ret = (px - o) / o * 100.0
            up = ret >= 0
            ext = fut.sess_high if up else fut.sess_low
            if ext <= 0:
                continue
            denom = (ext - o) if up else (o - ext)
            if denom <= 0:
                continue
            peak = denom / o * 100.0
            if peak < config.RSL_MIN_MOVE:
                continue
            retr = (((ext - px) if up else (px - ext)) / denom)
            if retr > config.RSL_MAX_RETR:
                continue
            rs = ret - basket
            drs = rs if up else -rs            # strength in its OWN direction
            if drs < config.RSL_RS_FLOOR:
                continue
            cands.append(RSLeader(
                ts=ts, underlying=ul, direction="BUY" if up else "SELL",
                rs=round(drs, 2), ret_pct=round(ret, 2),
                basket_pct=round(basket, 2), retrace=round(retr, 2),
                rank=0, fut_price=px))
        cands.sort(key=lambda r: -r.rs)
        top = cands[:config.RSL_TOP_N]
        for i, r in enumerate(top, 1):
            r.rank = i
        return top

    def maybe_lock(self, ts: datetime) -> list[RSLeader]:
        """At RSL_DECISION freeze the day's picks; returns them the first time only."""
        if (self._locked or ts.time() < config.RSL_DECISION
                or ts.time() > config.MARKET_CLOSE):
            return []
        picks = self.compute(ts)
        for r in picks:
            r.locked = True
        self.locked_picks = picks
        self._locked = True
        if picks:
            log.info("RS LEADERS (shadow) locked %s: %s", ts.strftime("%H:%M"),
                     ", ".join(f"#{r.rank} {r.underlying} {r.direction} "
                               f"rs={r.rs:+.2f} (stock {r.ret_pct:+.2f}% vs "
                               f"mkt {r.basket_pct:+.2f}%)" for r in picks))
        else:
            log.info("RS LEADERS (shadow) locked %s: no qualifying leader",
                     ts.strftime("%H:%M"))
        return picks
