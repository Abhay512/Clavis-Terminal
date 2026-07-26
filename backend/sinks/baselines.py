"""Cross-day per-stock flow baselines, stored as a trailing-median CSV."""
from __future__ import annotations

import csv
import logging
import statistics
from datetime import date

import config

log = logging.getLogger("baselines")

_HEADER = ["date", "underlying", "typical_net5_cr", "near_typical_cr"]


def _read_rows(path=None) -> list[dict]:
    path = path or config.FLOW_BASELINE_FILE
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("underlying")]


def _write_rows(rows: list[dict], path=None) -> None:
    path = path or config.FLOW_BASELINE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_HEADER)
        w.writeheader()
        w.writerows(rows)


def save_flow_baseline(day: date, oneway_engine, radar_engine,
                       path=None) -> int:
    """Append (or replace) the day's per-stock baselines; prune the file to
    the trailing BASELINE_TRAIL_DAYS dates. Returns stocks written."""
    day_s = day.isoformat()
    new_rows: list[dict] = []
    near_hist = getattr(radar_engine, "near_minute_hist", {})
    for ul, tr in oneway_engine._track.items():
        typical = 0.0
        if len(tr.absnet) >= config.BASELINE_MIN_SAMPLES:
            typical = statistics.median(tr.absnet)
        near = 0.0
        hist = near_hist.get(ul, [])
        if len(hist) >= config.BASELINE_MIN_SAMPLES:
            near = statistics.median(hist)
        if typical <= 0 and near <= 0:
            continue
        new_rows.append({"date": day_s, "underlying": ul,
                         "typical_net5_cr": f"{typical:.4f}",
                         "near_typical_cr": f"{near:.4f}"})
    if not new_rows:
        log.info("Flow baseline: nothing to save for %s (session too short).",
                 day_s)
        return 0
    rows = [r for r in _read_rows(path) if r["date"] != day_s] + new_rows
    dates = sorted({r["date"] for r in rows})
    keep = set(dates[-config.BASELINE_TRAIL_DAYS:])
    rows = [r for r in rows if r["date"] in keep]
    _write_rows(rows, path)
    log.info("Flow baseline saved: %d stocks for %s (%d dates on file).",
             len(new_rows), day_s, len(keep))
    return len(new_rows)


def load_flow_baseline(before: date | None = None, path=None
                       ) -> tuple[dict[str, float], dict[str, float]]:
    """(typical_map, near_map): per-stock trailing medians across the stored
    dates STRICTLY BEFORE `before` (no lookahead in replays; None = all)."""
    rows = _read_rows(path)
    if before is not None:
        rows = [r for r in rows if r["date"] < before.isoformat()]
    by_ul: dict[str, tuple[list[float], list[float]]] = {}
    for r in rows:
        t, n = by_ul.setdefault(r["underlying"], ([], []))
        try:
            tv = float(r["typical_net5_cr"])
            nv = float(r["near_typical_cr"])
        except ValueError:
            continue
        if tv > 0:
            t.append(tv)
        if nv > 0:
            n.append(nv)
    typical_map = {ul: statistics.median(t) for ul, (t, _) in by_ul.items()
                   if t}
    near_map = {ul: statistics.median(n) for ul, (_, n) in by_ul.items() if n}
    return typical_map, near_map
