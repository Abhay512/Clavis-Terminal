"""Offline replay of a recorded session through the same engine loop."""
from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

import config
from engine.bar_builder import Bar
from engine.big_player_radar import BigPlayerRadar
from engine.market_state import MarketState
from engine.oi_multiple import OIMultipleBoard, load_prev_eod_oi
from engine.oneway_momentum import OneWayMomentum
from engine.position_radar import PositionRadar
from engine.ranking import StockRanker
from engine.spike_detector import Signal, SpikeDetector
from sinks import signal_bus as sb
from sinks.storage import load_day_refs
from universe import Instrument, Universe, load_universe_csv

log = logging.getLogger("replay")

FORWARD_MINUTES = (15, 30)


def load_bars(day: date, bars_dir: Path | None = None) -> pd.DataFrame:
    d = (bars_dir or config.BARS_DIR) / day.isoformat()
    parts = sorted(d.glob("part_*.parquet"))
    if not parts:
        raise FileNotFoundError(f"No bar files under {d}")
    df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    if "backfilled" not in df.columns:
        df["backfilled"] = 0
    else:
        df["backfilled"] = df["backfilled"].fillna(0).astype(int)
    df.sort_values(["minute", "token"], inplace=True)
    log.info("Loaded %d bar rows for %s (%d instruments)",
             len(df), day, df["token"].nunique())
    return df


def load_or_build_universe(day: date, df: pd.DataFrame,
                           meta_dir: Path | None = None) -> Universe:
    path = (meta_dir or config.META_DIR) / f"{day.isoformat()}_universe.csv"
    if path.exists():
        return load_universe_csv(path)
    log.warning("Universe snapshot %s missing - rebuilding from bars "
                "(lot sizes unknown, min-OI filter weakened).", path)
    uni = Universe()
    meta = df.drop_duplicates("token")
    for row in meta.itertuples():
        uni.instruments.append(Instrument(
            token=int(row.token), tradingsymbol=row.tradingsymbol,
            underlying=row.underlying, kind=row.kind,
            strike=float(row.strike), lot_size=1, expiry=day))
    uni.finalize()
    return uni


def replay_day(day: date, rank_every: int = 15, save: bool = False,
               bars_dir: Path | None = None,
               meta_dir: Path | None = None,
               save_baseline: bool = False) -> list[Signal]:
    df = load_bars(day, bars_dir)
    universe = load_or_build_universe(day, df, meta_dir)
    market = MarketState(universe)
    n_refs = load_day_refs(market, day)
    if n_refs:
        log.info("Loaded day refs (prev close/open) for %d instruments - "
                 "day %% matches the live session.", n_refs)
    else:
        log.warning("No day refs for %s - day %% falls back to first-seen "
                    "price (older recordings).", day)
    detector = SpikeDetector(market)
    ranker = StockRanker(market)
    position_engine = PositionRadar(market)
    from sinks.baselines import load_flow_baseline
    typical_map, near_map = load_flow_baseline(before=day)
    if typical_map:
        log.info("Flow baselines loaded for %d stocks (prior days).",
                 len(typical_map))
    else:
        log.warning("No prior-day flow baselines for %s - loader flag uses "
                    "the absolute branch; build_x uses session medians.", day)
    oneway_engine = OneWayMomentum(market, flow_baseline=typical_map,
                                   near_baseline=near_map)
    radar_engine = BigPlayerRadar(market)
    oimult_engine = OIMultipleBoard(market, prev_eod=load_prev_eod_oi(day))

    bus = sb.SignalBus()
    signals: list[Signal] = []
    bus.on_signal(sb.print_signal)
    bus.on_signal(signals.append)
    bus.on_ranking(lambda rows: sb.print_rankings(rows))
    if save:
        from sinks.storage import SignalStore
        store = SignalStore()
        bus.on_signal(store.save_signal)
        bus.on_ranking(store.save_rankings)
        bus.on_position(store.save_position)
        bus.on_oneway(store.save_oneway)
        bus.on_radar(store.save_radar)
        bus.on_oimult(store.save_oimult)

    minute_count = 0
    for minute, group in df.groupby("minute", sort=True):
        touched = []
        for row in group.itertuples():
            state = market.by_token.get(int(row.token))
            if state is None:
                continue
            bar = Bar(minute=minute.to_pydatetime(), open=row.open,
                      high=row.high, low=row.low, close=row.close,
                      volume=int(row.volume), oi=int(row.oi),
                      oi_delta=int(row.oi_delta),
                      artifact=bool(row.backfilled == 2))
            state.bars.append(bar)
            state.bars_seen += 1
            state.last_price = bar.close
            state.last_oi = bar.oi
            if bar.high > state.sess_high:
                state.sess_high = bar.high
            if state.sess_low <= 0 or bar.low < state.sess_low:
                state.sess_low = bar.low
            if state.day_open <= 0:
                state.day_open = bar.open
            state._refresh_baseline()
            touched.append((state, bar))

        bar_ts = minute.to_pydatetime() + timedelta(minutes=1)
        for state, bar in touched:
            if bar.volume <= 0 and bar.oi_delta == 0:
                continue
            sig = detector.check(state, bar_ts, intrabar=False)
            if sig is not None:
                bus.publish_signal(sig)
        minute_count += 1
        at_cadence = rank_every > 0 and minute_count % rank_every == 0
        rows = ranker.compute(bar_ts)
        builds = position_engine.compute(rows, bar_ts)
        if builds:
            bus.publish_position(builds)
            if at_cadence:
                sb.print_position(builds)
        radar_sigs = radar_engine.compute(bar_ts)
        if radar_sigs:
            bus.publish_radar(radar_sigs)
            if at_cadence:
                sb.print_radar(radar_sigs)
        movers = oneway_engine.compute(rows, bar_ts, radar=radar_sigs,
                                       near=radar_engine.near_flows)
        if movers:
            bus.publish_oneway(movers)
            if at_cadence or any(m.status in ("ENTRY", "EXIT")
                                 for m in movers):
                sb.print_oneway(movers)
        oimult = oimult_engine.compute(bar_ts)
        if oimult:
            bus.publish_oimult(oimult)
            if at_cadence:
                sb.print_oimult(oimult)
        if at_cadence and rows:
            bus.publish_ranking(rows)

    print(f"\nReplay done: {minute_count} minutes, "
          f"{len(signals)} signals fired.")
    if save_baseline:
        from sinks.baselines import save_flow_baseline
        save_flow_baseline(day, oneway_engine, radar_engine)
    forward_return_report(signals, df)
    return signals


def forward_return_report(signals: list[Signal], df: pd.DataFrame) -> None:
    """For each signal: how did the underlying FUTURE move afterwards?"""
    if not signals:
        print("No signals - nothing to evaluate.")
        return
    futs = df[df["kind"] == "FUT"]
    fut_close: dict[tuple[str, datetime], float] = {
        (r.underlying, r.minute.to_pydatetime()): r.close
        for r in futs.itertuples()
    }

    rows = []
    for s in signals:
        base_minute = s.ts.replace(second=0, microsecond=0)
        p0 = fut_close.get((s.underlying, base_minute))
        if p0 is None or p0 <= 0:
            continue
        row = {"underlying": s.underlying, "kind": s.kind,
               "classification": s.classification, "side": s.side or "FUT",
               "score": s.score}
        ok = False
        for fm in FORWARD_MINUTES:
            p1 = fut_close.get((s.underlying,
                                base_minute + timedelta(minutes=fm)))
            if p1 is not None and p1 > 0:
                row[f"fwd_{fm}m_pct"] = (p1 - p0) / p0 * 100.0
                ok = True
        if ok:
            rows.append(row)
    if not rows:
        print("No forward data available for the fired signals.")
        return

    rep = pd.DataFrame(rows)
    print("\n========== FORWARD RETURN REPORT (underlying futures) ==========")
    for fm in FORWARD_MINUTES:
        col = f"fwd_{fm}m_pct"
        if col not in rep.columns:
            continue
        agg = rep.groupby(["kind", "classification"])[col] \
                 .agg(["count", "mean", "median"]).round(3)
        print(f"\n--- {fm} minutes after signal ---")
        print(agg.to_string())
    print("\nReading guide: LONG_BUILDUP (buy side) should show positive "
          "mean forward move,\nSHORT_BUILDUP (sell side/writing) negative. "
          "Flat means the signal has no edge yet - tune config.py.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay recorded bars "
                                                 "through the OI engine")
    parser.add_argument("--date", default=date.today().isoformat(),
                        help="session date YYYY-MM-DD (default today)")
    parser.add_argument("--rank-every", type=int, default=15,
                        help="print ranking tables every N minutes "
                             "(0 disables)")
    parser.add_argument("--save", action="store_true",
                        help="also persist replayed signals to SQLite")
    parser.add_argument("--save-baseline", action="store_true",
                        help="write this day's per-stock flow baselines to "
                             "data/meta/flow_baseline.csv (used to seed the "
                             "engines with prior-day 'typical' flow)")
    args = parser.parse_args()
    logging.basicConfig(level=config.LOG_LEVEL,
                        format="%(levelname)s %(name)s %(message)s")
    replay_day(date.fromisoformat(args.date), rank_every=args.rank_every,
               save=args.save, save_baseline=args.save_baseline)
