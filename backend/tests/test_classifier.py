"""Tests for OI flow classification and four-way flow totals.

Run from the backend directory:

    python -m tests.test_classifier
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import classifier  # noqa: E402
from engine.ranking import StockRank, flows_4way  # noqa: E402


def _rank() -> StockRank:
    return StockRank(
        ts=datetime(2026, 1, 5, 9, 20),
        underlying="TEST",
        fut_price=1000.0,
        price_pct_day=1.0,
        fut_classification=classifier.LONG_BUILDUP,
        buy_units=0,
        sell_units=0,
        buy_notional_cr=0.0,
        sell_notional_cr=0.0,
        ce_buy_cr=1.0,
        pe_buy_cr=2.0,
        ce_write_cr=4.0,
        pe_write_cr=8.0,
        ce_cover_cr=16.0,
        pe_cover_cr=32.0,
        ce_unwind_cr=64.0,
        pe_unwind_cr=128.0,
        top_buy_strike="",
        top_sell_strike="",
        top_ce_buy_strike="",
        top_pe_buy_strike="",
    )


def test_classify_directional_branches() -> None:
    cases = [
        (100, 1.0, classifier.LONG_BUILDUP),
        (100, -1.0, classifier.SHORT_BUILDUP),
        (-100, 1.0, classifier.SHORT_COVERING),
        (-100, -1.0, classifier.LONG_UNWINDING),
    ]

    for oi_delta, price_pct, expected in cases:
        assert classifier.classify(oi_delta, price_pct) == expected


def test_classify_zero_change_is_neutral() -> None:
    assert classifier.classify(0, 1.0) == classifier.NEUTRAL
    assert classifier.classify(100, 0.0) == classifier.NEUTRAL


def test_flows_4way_totals() -> None:
    bullish, bearish = flows_4way(_rank())

    assert bullish == 153.0
    assert bearish == 102.0


def main() -> int:
    tests = [
        test_classify_directional_branches,
        test_classify_zero_change_is_neutral,
        test_flows_4way_totals,
    ]

    for test in tests:
        test()
        print(f"  [PASS] {test.__name__}")
    print(f"\n{len(tests)}/{len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
