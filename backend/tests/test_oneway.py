"""Smoke tests for the reference one-way board.

Run from the backend directory:

    python -m tests.test_oneway
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.market_state import MarketState  # noqa: E402
from engine.oneway_momentum import OneWayMomentum  # noqa: E402
from engine.ranking import StockRank  # noqa: E402
from universe import Instrument, Universe  # noqa: E402

START = datetime(2026, 1, 5, 9, 20)


def _universe(symbols: list[str]) -> Universe:
    u = Universe()
    for i, sym in enumerate(symbols, 1):
        u.instruments.append(Instrument(
            token=i, tradingsymbol=f"{sym}FUT", underlying=sym, kind="FUT",
            strike=0.0, lot_size=100, expiry=date(2026, 1, 29)))
    u.finalize()
    return u


def _rank(sym: str, ts: datetime, px: float, bull: float, bear: float,
          day_pct: float) -> StockRank:
    return StockRank(
        ts=ts, underlying=sym, fut_price=px, price_pct_day=day_pct,
        fut_classification="LONG_BUILDUP",
        buy_units=0, sell_units=0,
        buy_notional_cr=bull, sell_notional_cr=bear,
        ce_buy_cr=bull, pe_buy_cr=bear, ce_write_cr=0.0, pe_write_cr=0.0,
        ce_cover_cr=0.0, pe_cover_cr=0.0, ce_unwind_cr=0.0, pe_unwind_cr=0.0,
        top_buy_strike="1500CE +80000", top_sell_strike="1400PE +40000",
        top_ce_buy_strike="1500CE", top_pe_buy_strike="1400PE")


def _run(minutes: int = 60):
    """Drive the engine with a clean riser and a choppy name side by side."""
    market = MarketState(_universe(["CLEAN", "CHOP"]))
    engine = OneWayMomentum(market, flow_baseline={"CLEAN": 1.0, "CHOP": 1.0})
    seen = []
    clean_px, chop_px = 1000.0, 1000.0

    for i in range(minutes):
        ts = START + timedelta(minutes=i)
        clean_px *= 1.0012
        chop_px *= 1.004 if i % 2 else 0.996
        rows = [
            _rank("CLEAN", ts, clean_px, 6.0, 0.4,
                  (clean_px - 1000) / 10),
            _rank("CHOP", ts, chop_px,
                  6.0 if i % 2 else 0.4, 0.4 if i % 2 else 6.0,
                  (chop_px - 1000) / 10),
        ]
        seen.extend(engine.compute(rows, ts))
    return engine, seen


def main() -> int:
    engine, movers = _run()
    checks: list[tuple[str, bool]] = []

    entries = [m for m in movers if m.status == "ENTRY"]
    checks.append(("the clean riser is entered",
                   any(m.underlying == "CLEAN" for m in entries)))
    checks.append(("the choppy name is rejected",
                   not any(m.underlying == "CHOP" for m in entries)))
    checks.append(("entries are directional",
                   all(m.direction in ("BUY", "SELL") for m in entries)))
    checks.append(("every mover carries a score",
                   all(0.0 <= m.score <= 100.0 for m in movers)))
    checks.append(("open rides report live P&L",
                   any(m.status == "OPEN" and m.pnl_pct > 0 for m in movers)))
    checks.append(("the promotion meter stays in range",
                   all(0.0 <= m.promo_pct <= 100.0 for m in movers)))
    checks.append(("baseline samples are collected",
                   len(engine._track["CLEAN"].absnet) > 0))

    promoted = [m for m in movers if m.conviction]
    checks.append(("a sustained winner reaches the top board",
                   bool(promoted)))
    checks.append(("promotion never precedes its P&L floor",
                   all(m.pnl_pct >= 0 for m in promoted)))

    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    failed = sum(not ok for _, ok in checks)
    print(f"\n{len(checks) - failed}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
