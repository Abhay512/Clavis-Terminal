"""Per-stock buy-side / sell-side OI build-up ranking in rupee notional."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from engine import classifier, oi_engine
from engine.market_state import MarketState
from engine.spike_detector import SIGNAL_WINDOW

log = logging.getLogger("ranking")


@dataclass(slots=True)
class StockRank:
    ts: datetime
    underlying: str
    fut_price: float             # live futures price (underlying proxy)
    price_pct_day: float
    fut_classification: str      # futures build-up context
    buy_units: int               # option buy-side OI added (underlying units)
    sell_units: int              # option sell-side (writing) OI added
    buy_notional_cr: float
    sell_notional_cr: float
    ce_buy_cr: float             # call buying        (bullish)
    pe_buy_cr: float             # put buying         (bearish)
    ce_write_cr: float           # call writing       (bearish)
    pe_write_cr: float           # put writing        (bullish)
    # OI-decrease flows (same classify() logic on falling OI)
    ce_cover_cr: float           # call short-covering (bullish exit fuel)
    pe_cover_cr: float           # put short-covering  (bearish exit fuel)
    ce_unwind_cr: float          # call long-unwinding (bearish)
    pe_unwind_cr: float          # put long-unwinding  (bullish)
    top_buy_strike: str          # e.g. "1450CE +120000"
    top_sell_strike: str
    top_ce_buy_strike: str       # strongest call-buying strike (BUY ideas)
    top_pe_buy_strike: str       # strongest put-buying strike  (SELL ideas)


def flows_4way(r: "StockRank") -> tuple[float, float]:
    """Combined bullish / bearish rupee flow across all four OI angles."""
    bull = r.ce_buy_cr + r.pe_write_cr + r.ce_cover_cr + r.pe_unwind_cr
    bear = r.pe_buy_cr + r.ce_write_cr + r.pe_cover_cr + r.ce_unwind_cr
    return bull, bear


def _roll_transfer(exits: list[tuple[float, int]],
                   builds: list[tuple[float, int]], up: bool) -> int:
    """A same-side unwind plus a build at a further strike is a roll, not new money."""
    if not exits or not builds:
        return 0
    if up:
        u = sum(m for k, m in exits if any(bk > k for bk, _ in builds))
        b = sum(m for bk, m in builds if any(k < bk for k, _ in exits))
    else:
        u = sum(m for k, m in exits if any(bk < k for bk, _ in builds))
        b = sum(m for bk, m in builds if any(k > bk for k, _ in exits))
    return min(u, b)


class StockRanker:
    def __init__(self, market: MarketState):
        self.market = market

    def compute(self, ts: datetime) -> list[StockRank]:
        rows: list[StockRank] = []
        for underlying, opt_states in self.market.options_by_underlying.items():
            fut_price = self.market.underlying_price(underlying)
            buy_units = sell_units = 0
            ce_buy = pe_buy = ce_write = pe_write = 0    # units
            ce_cover = pe_cover = ce_unwind = pe_unwind = 0
            ce_buys: list[tuple[float, int]] = []
            pe_buys: list[tuple[float, int]] = []
            ce_writes: list[tuple[float, int]] = []
            pe_writes: list[tuple[float, int]] = []
            ce_unwinds: list[tuple[float, int]] = []
            pe_unwinds: list[tuple[float, int]] = []
            ce_covers: list[tuple[float, int]] = []
            pe_covers: list[tuple[float, int]] = []
            top_buy = (0, "")     # (oi_delta, label)
            top_sell = (0, "")
            top_ce_buy = (0, "")
            top_pe_buy = (0, "")
            for state in opt_states:
                m = oi_engine.compute(state, SIGNAL_WINDOW, intrabar=False)
                if m is None or m.oi_delta == 0:
                    continue
                cls = classifier.classify(m.oi_delta, m.price_pct)
                kind = state.inst.kind
                strike = state.inst.strike
                if m.oi_delta < 0:
                    # positions EXITING - covering / unwinding flows
                    mag = -m.oi_delta
                    if cls == classifier.SHORT_COVERING:
                        if kind == "CE":
                            ce_cover += mag
                            ce_covers.append((strike, mag))
                        else:
                            pe_cover += mag
                            pe_covers.append((strike, mag))
                    elif cls == classifier.LONG_UNWINDING:
                        if kind == "CE":
                            ce_unwind += mag
                            ce_unwinds.append((strike, mag))
                        else:
                            pe_unwind += mag
                            pe_unwinds.append((strike, mag))
                    continue
                side = classifier.option_side(cls)
                label = f"{state.inst.strike:g}{kind} +{m.oi_delta}"
                if side == classifier.BUY_SIDE:
                    buy_units += m.oi_delta
                    if m.oi_delta > top_buy[0]:
                        top_buy = (m.oi_delta, label)
                    if kind == "CE":
                        ce_buy += m.oi_delta
                        ce_buys.append((strike, m.oi_delta))
                        if m.oi_delta > top_ce_buy[0]:
                            top_ce_buy = (m.oi_delta, label)
                    else:
                        pe_buy += m.oi_delta
                        pe_buys.append((strike, m.oi_delta))
                        if m.oi_delta > top_pe_buy[0]:
                            top_pe_buy = (m.oi_delta, label)
                elif side == classifier.SELL_SIDE:
                    sell_units += m.oi_delta
                    if m.oi_delta > top_sell[0]:
                        top_sell = (m.oi_delta, label)
                    if kind == "CE":
                        ce_write += m.oi_delta
                        ce_writes.append((strike, m.oi_delta))
                    else:
                        pe_write += m.oi_delta
                        pe_writes.append((strike, m.oi_delta))

            ce_unwind -= _roll_transfer(ce_unwinds, ce_buys, up=True)
            pe_unwind -= _roll_transfer(pe_unwinds, pe_buys, up=False)
            pe_cover -= _roll_transfer(pe_covers, pe_writes, up=True)
            ce_cover -= _roll_transfer(ce_covers, ce_writes, up=False)

            if (buy_units == 0 and sell_units == 0 and ce_cover == 0
                    and pe_cover == 0 and ce_unwind == 0 and pe_unwind == 0):
                continue

            fut_state = self.market.futures_by_underlying.get(underlying)
            fut_cls = classifier.NEUTRAL
            day_pct = 0.0
            if fut_state is not None:
                day_pct = fut_state.day_pct()
                fm = oi_engine.compute(fut_state, SIGNAL_WINDOW)
                if fm is not None:
                    fut_cls = classifier.classify(fm.oi_delta, fm.price_pct)

            to_cr = fut_price / 1e7
            rows.append(StockRank(
                ts=ts, underlying=underlying, fut_price=fut_price,
                price_pct_day=round(day_pct, 2),
                fut_classification=fut_cls,
                buy_units=buy_units, sell_units=sell_units,
                buy_notional_cr=round(buy_units * to_cr, 2),
                sell_notional_cr=round(sell_units * to_cr, 2),
                ce_buy_cr=round(ce_buy * to_cr, 2),
                pe_buy_cr=round(pe_buy * to_cr, 2),
                ce_write_cr=round(ce_write * to_cr, 2),
                pe_write_cr=round(pe_write * to_cr, 2),
                ce_cover_cr=round(ce_cover * to_cr, 2),
                pe_cover_cr=round(pe_cover * to_cr, 2),
                ce_unwind_cr=round(ce_unwind * to_cr, 2),
                pe_unwind_cr=round(pe_unwind * to_cr, 2),
                top_buy_strike=top_buy[1], top_sell_strike=top_sell[1],
                top_ce_buy_strike=top_ce_buy[1],
                top_pe_buy_strike=top_pe_buy[1],
            ))
        return rows

    @staticmethod
    def top_buy(rows: list[StockRank], n: int = 10) -> list[StockRank]:
        return sorted(rows, key=lambda r: r.buy_notional_cr, reverse=True)[:n]

    @staticmethod
    def top_sell(rows: list[StockRank], n: int = 10) -> list[StockRank]:
        return sorted(rows, key=lambda r: r.sell_notional_cr, reverse=True)[:n]
