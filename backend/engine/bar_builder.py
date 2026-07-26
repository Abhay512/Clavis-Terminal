"""1-minute OHLCV+OI bar construction from raw ticks."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Bar:
    minute: datetime          # bar start, second == 0
    open: float
    high: float
    low: float
    close: float
    volume: int               # traded volume within this minute
    oi: int                   # OI at end of minute
    oi_delta: int             # oi - previous bar's oi
    artifact: bool = False


@dataclass(slots=True)
class WorkingBar:
    minute: datetime
    open: float
    high: float
    low: float
    close: float
    vol_start: int            # cumulative day volume when the bar opened
    vol_end: int
    oi: int


def open_bar(minute: datetime, price: float, cum_volume: int, oi: int) -> WorkingBar:
    return WorkingBar(minute=minute, open=price, high=price, low=price,
                      close=price, vol_start=cum_volume, vol_end=cum_volume,
                      oi=oi)


def update_bar(wb: WorkingBar, price: float, cum_volume: int, oi: int) -> None:
    if price > wb.high:
        wb.high = price
    if price < wb.low:
        wb.low = price
    wb.close = price
    if cum_volume > wb.vol_end:
        wb.vol_end = cum_volume
    if oi > 0:
        wb.oi = oi


def close_bar(wb: WorkingBar, prev_oi: int | None) -> Bar:
    oi_delta = 0 if prev_oi is None else wb.oi - prev_oi
    return Bar(minute=wb.minute, open=wb.open, high=wb.high, low=wb.low,
               close=wb.close, volume=max(0, wb.vol_end - wb.vol_start),
               oi=wb.oi, oi_delta=oi_delta)


def carry_bar(minute: datetime, prev: Bar) -> Bar:
    """Synthetic bar for a minute with no ticks - keeps series continuous."""
    return Bar(minute=minute, open=prev.close, high=prev.close,
               low=prev.close, close=prev.close, volume=0,
               oi=prev.oi, oi_delta=0)
