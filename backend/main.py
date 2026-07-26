"""Live screener orchestrator: auth, universe, feed, per-minute engine loop."""
from __future__ import annotations

import argparse
import atexit
import logging
import os
import sys
import threading
import time as time_mod
from datetime import date, datetime, time, timedelta

import config
from auth import get_kite
from engine.big_player_radar import BigPlayerRadar
from engine.market_state import MarketState
from engine.oi_multiple import OIMultipleBoard
from engine.oneway_momentum import OneWayMomentum
from engine.position_radar import PositionRadar
from engine.ranking import StockRanker
from engine.rs_leaders import RSLeaders
from engine.sector_leaders import SectorLeaders
from engine.spike_detector import SpikeDetector
from feed.backfill import BackfillWorker, fetch_futures_bars, to_parquet_rows
from feed.tick_queue import TickQueue
from feed.ticker_manager import TickerManager
from sinks import signal_bus as sb
from sinks.baselines import load_flow_baseline, save_flow_baseline
from sinks.storage import BarWriter, SignalStore, save_day_refs, save_eod_oi_snapshot
from universe import build_universe, save_universe_csv

log = logging.getLogger("main")

CLOSE_GRACE_SECONDS = 2   # wait this long past minute end before closing bars
RANK_TOP_N = 10

LOCK_FILE = config.META_DIR / "screener.lock"


def _process_alive(pid: int) -> bool:
    """True if a process with `pid` is currently running (Windows + POSIX)."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        k = ctypes.windll.kernel32
        h = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == STILL_ACTIVE
    try:
        os.kill(pid, 0)          # signal 0 = liveness probe on POSIX
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _release_lock() -> None:
    try:
        if LOCK_FILE.exists() and \
                int(LOCK_FILE.read_text().strip() or "0") == os.getpid():
            LOCK_FILE.unlink()
    except Exception:
        pass


def acquire_single_instance_lock() -> None:
    config.ensure_dirs()
    if LOCK_FILE.exists():
        try:
            other = int(LOCK_FILE.read_text().strip() or "0")
        except ValueError:
            other = 0
        if other and other != os.getpid() and _process_alive(other):
            print("=" * 70)
            print(f" ANOTHER SCREENER IS ALREADY RUNNING (PID {other}).")
            print(" Run only ONE `python main.py` at a time.")
            print("")
            print(" Your Kite API key allows just 3 WebSocket connections in")
            print(" total, and one screener already uses all 3 to watch every")
            print(" stock. A second screener steals connections from the first,")
            print(" so each terminal then shows a DIFFERENT, partial set of")
            print(" stocks - this is exactly that bug.")
            print("")
            print(" Correct setup: ONE terminal for `python main.py --api`,")
            print(" and (optionally) ONE terminal for `npm run dev` in dashboard/.")
            print(f" If the previous run crashed, delete {LOCK_FILE} and retry.")
            print("=" * 70)
            sys.exit(1)
        # stale lock (previous run crashed) - take it over
        log.warning("Removing stale screener lock (PID %d not running).", other)
    LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
    atexit.register(_release_lock)
    log.info("Single-instance lock acquired (PID %d).", os.getpid())


def wait_for_open(start_now: bool) -> None:
    if start_now:
        return
    now = datetime.now()
    open_dt = datetime.combine(date.today(), config.MARKET_OPEN)
    if now.time() >= config.SHUTDOWN_AT:
        print("Market is closed for today. Use --now to run anyway "
              "(e.g. for testing).")
        sys.exit(0)
    while datetime.now() < open_dt:
        remaining = (open_dt - datetime.now()).total_seconds()
        log.info("Waiting for market open 09:15 (%d s remaining)...",
                 int(remaining))
        time_mod.sleep(min(30, max(1, remaining)))


def warm_start(market, ranker, position_engine, oneway_engine,
               radar_engine, bus, store, kite=None, bar_writer=None,
               day=None, until=None, oimult_engine=None) -> datetime | None:
    """Rebuild today's state from bars already recorded, so a mid-day restart resumes."""
    from datetime import date as _date

    from engine.bar_builder import Bar
    from sinks.storage import load_day_refs
    day = day or _date.today()
    try:
        from replay import load_bars
        df = load_bars(day)
    except FileNotFoundError:
        log.info("Warm-start: no bars recorded yet today - starting fresh.")
        return None
    now_min = until or datetime.now().replace(second=0, microsecond=0)
    df = df[(df["minute"] >= day.isoformat()) & (df["minute"] < now_min)]
    if df.empty:
        return None
    load_day_refs(market, day)                # correct day% from saved refs

    gap_start = None
    last_rec = df["minute"].max().to_pydatetime()
    down_gap = (now_min - last_rec) >= timedelta(
        minutes=config.BACKFILL_MIN_GAP_MIN + 1)
    in_session = (config.MARKET_OPEN <= now_min.time() <= config.MARKET_CLOSE)
    if down_gap and in_session:
        gap_start = last_rec + timedelta(minutes=1)
        if kite is not None:
            try:
                fetched = fetch_futures_bars(kite, market, gap_start,
                                             now_min - timedelta(minutes=1))
                if fetched:
                    import pandas as pd
                    rows = to_parquet_rows(market, fetched)
                    if bar_writer is not None:
                        bar_writer.add_backfill(rows)   # -> parquet, bf=1
                    cols = ["minute", "token", "tradingsymbol", "underlying",
                            "kind", "strike", "open", "high", "low", "close",
                            "volume", "oi", "oi_delta", "backfilled"]
                    add = pd.DataFrame(rows, columns=cols)
                    add["minute"] = pd.to_datetime(add["minute"])
                    df = pd.concat([df, add], ignore_index=True)
                    df.sort_values(["minute", "token"], inplace=True)
            except Exception:
                log.exception("restart backfill failed - continuing without")

    n_min = df["minute"].nunique()
    log.info("Warm-start: replaying %d recorded minutes to rebuild state...",
             n_min)
    has_bf = "backfilled" in df.columns

    last = {"rows": None, "builds": None, "movers": None, "radar": None,
            "oimult": None}
    for minute, group in df.groupby("minute", sort=True):
        for row in group.itertuples():
            st = market.by_token.get(int(row.token))
            if st is None:
                continue
            bar = Bar(minute=minute.to_pydatetime(), open=row.open,
                      high=row.high, low=row.low, close=row.close,
                      volume=int(row.volume), oi=int(row.oi),
                      oi_delta=int(row.oi_delta),
                      artifact=bool(has_bf and row.backfilled == 2))
            st.bars.append(bar)
            st.bars_seen += 1
            st.last_price = bar.close
            st.last_oi = bar.oi
            if bar.high > st.sess_high:
                st.sess_high = bar.high
            if st.sess_low <= 0 or bar.low < st.sess_low:
                st.sess_low = bar.low
            if st.day_open <= 0:
                st.day_open = bar.open
            st._refresh_baseline()
        bar_ts = minute.to_pydatetime() + timedelta(minutes=1)
        rows = ranker.compute(bar_ts)
        if rows:
            builds = position_engine.compute(rows, bar_ts)
            radar_sigs = radar_engine.compute(bar_ts)
            movers = oneway_engine.compute(rows, bar_ts, radar=radar_sigs,
                                           near=radar_engine.near_flows)
            oimult = (oimult_engine.compute(bar_ts)
                      if oimult_engine is not None else None)
            last.update(rows=rows, builds=builds, movers=movers,
                        radar=radar_sigs, oimult=oimult)

    if last["rows"]:
        bus.publish_ranking(last["rows"])
    if last["builds"]:
        bus.publish_position(last["builds"])
    if last["movers"]:
        bus.publish_oneway([m for m in last["movers"] if m.status != "EXIT"])
    if last["radar"]:
        bus.publish_radar(last["radar"])
    if last["oimult"]:
        bus.publish_oimult(last["oimult"])
    log.info("Warm-start done: state rebuilt to %s. Open one-way movers: %d.",
             now_min.strftime("%H:%M"), len(oneway_engine._open))
    return gap_start


def run(start_now: bool = False,
        api_starter=None, warm: bool = True) -> None:
    config.ensure_dirs()
    acquire_single_instance_lock()   # refuse to start a second live screener
    _now = datetime.now()
    if time(9, 20) < _now.time() < time(15, 30) and _now.weekday() < 5:
        log.warning("=" * 68)
        log.warning("LATE START (%s): options have NO backfill - the opening "
                    "window is lost and early radar direction reads will be "
                    "unreliable for ~30 min. Loader flags and the OI-multiple "
                    "board baselines are degraded today. Start the screener "
                    "by 09:10 tomorrow.", _now.strftime("%H:%M"))
        log.warning("=" * 68)
    kite = get_kite(interactive=True)
    symbols = config.load_stock_list()
    log.info("Monitoring %d stocks from %s", len(symbols), config.STOCKS_FILE)

    universe = build_universe(kite, symbols)
    if not universe.instruments:
        log.error("Universe is empty - check stocks.txt symbols.")
        sys.exit(1)
    save_universe_csv(universe)

    market = MarketState(universe)
    detector = SpikeDetector(market)
    ranker = StockRanker(market)
    position_engine = PositionRadar(market)
    typical_map, near_map = load_flow_baseline(before=date.today())
    log.info("Flow baselines loaded: %d stocks (all-strikes), %d (near-spot) "
             "from %s", len(typical_map), len(near_map),
             config.FLOW_BASELINE_FILE.name)
    oneway_engine = OneWayMomentum(market, flow_baseline=typical_map,
                                   near_baseline=near_map)
    radar_engine = BigPlayerRadar(market)
    oimult_engine = OIMultipleBoard(market)
    rs_leaders = RSLeaders(market)      # shadow: records picks, trades nothing
    sector_leaders = SectorLeaders(market)  # shadow: sector-leader board, trades nothing

    bus = sb.SignalBus()
    store = SignalStore()
    bus.on_signal(sb.print_signal)
    bus.on_signal(store.save_signal)
    bus.on_ranking(lambda rows: sb.print_rankings(rows, RANK_TOP_N))
    bus.on_ranking(store.save_rankings)
    bus.on_position(sb.print_position)
    bus.on_position(store.save_position)
    bus.on_oneway(sb.print_oneway)
    bus.on_oneway(store.save_oneway)
    bus.on_radar(store.save_radar)
    bus.on_oimult(store.save_oimult)

    bar_writer = BarWriter()
    bar_writer.start_background()

    if api_starter is not None:
        api_thread = threading.Thread(
            target=api_starter, args=(bus, store, len(universe.instruments)),
            name="api-server", daemon=True)
        api_thread.start()
        log.info("Dashboard API started on port 8000 - open http://localhost:3000")

    env = config.load_env()
    tick_queue = TickQueue()
    ticker = TickerManager(env["KITE_API_KEY"], env["KITE_ACCESS_TOKEN"],
                           universe.tokens(), tick_queue)

    wait_for_open(start_now)

    restart_gap_start = None
    if warm:
        restart_gap_start = warm_start(market, ranker, position_engine,
                                       oneway_engine, radar_engine, bus,
                                       store, kite=kite,
                                       bar_writer=bar_writer,
                                       oimult_engine=oimult_engine)

    ticker.start()
    log.info("Live. Consuming ticks for %d instruments.",
             len(universe.instruments))

    backfiller = BackfillWorker(kite, market)

    pending_minute = datetime.now().replace(second=0, microsecond=0)
    signals_fired = 0
    position_had = False
    oneway_had = False
    radar_had = False
    oimult_had = False
    sector_had = False
    day_refs_saved = False

    # ---- feed watchdog state ----------------------------------------------
    last_tick_mono = time_mod.monotonic()
    last_tick_wall = datetime.now()
    last_kick_mono = time_mod.monotonic()
    gap_start: datetime | None = restart_gap_start   # open outage (if any);
    #                              closed at the first live tick batch
    reconnects = 0
    feed_down_flagged = False
    artifact_ranges: list[tuple[datetime, datetime]] = []

    def _in_artifact_range(minute: datetime) -> bool:
        return any(s <= minute <= e for s, e in artifact_ranges)

    try:
        while datetime.now().time() < config.SHUTDOWN_AT:
            ticks = tick_queue.drain(timeout=0.2)
            now_wall = datetime.now()
            market_hours = (config.MARKET_OPEN <= now_wall.time()
                            <= config.MARKET_CLOSE)
            if ticks:
                if gap_start is not None:
                    # feed recovered: record the outage, mark the catch-up
                    # window artifact (option OI lands as one delta), and
                    end_min = now_wall.replace(second=0, microsecond=0)
                    recovered = ("restart" if restart_gap_start is not None
                                 and gap_start == restart_gap_start
                                 else f"watchdog-reconnect-{reconnects}")
                    store.save_feed_gap(gap_start, now_wall, recovered)
                    artifact_ranges.append(
                        (gap_start.replace(second=0, microsecond=0),
                         end_min + timedelta(
                             minutes=config.ARTIFACT_PAD_MIN)))
                    if recovered != "restart":   # restart path backfilled
                        backfiller.request(gap_start, now_wall)
                    gap_start = None
                    restart_gap_start = None
                    reconnects = 0
                    if feed_down_flagged:
                        feed_down_flagged = False
                        bus.publish_feed({"feed_down": False, "feed_note": ""})
                last_tick_mono = time_mod.monotonic()
                last_tick_wall = now_wall
            elif (market_hours
                  and time_mod.monotonic() - last_tick_mono
                  > config.FEED_STALE_SECONDS
                  and time_mod.monotonic() - last_kick_mono
                  > config.FEED_STALE_SECONDS):
                if gap_start is None:
                    gap_start = last_tick_wall
                reconnects += 1
                log.critical(
                    "FEED WATCHDOG: no ticks for %.0fs during market hours "
                    "- forcing reconnect (attempt %d)",
                    time_mod.monotonic() - last_tick_mono, reconnects)
                if reconnects >= config.FEED_RECONNECT_MAX:
                    # repeated failures usually mean the access token died
                    # (expired token = endless reconnect loop) - re-check it
                    note = (f"feed silent since "
                            f"{last_tick_wall.strftime('%H:%M:%S')}, "
                            f"{reconnects} reconnects failed")
                    try:
                        kite2 = get_kite(interactive=False)
                        fresh = config.load_env().get("KITE_ACCESS_TOKEN", "")
                        ticker.force_reconnect(access_token=fresh or None)
                        del kite2
                    except ConnectionError as e:
                        # re-auth. Just keep recycling the sockets.
                        note += " - Kite unreachable (network), retrying"
                        log.critical("FEED WATCHDOG: Kite unreachable (network) - "
                                     "retrying; token likely valid (%s)", e)
                        ticker.force_reconnect()
                    except Exception:
                        note += " - ACCESS TOKEN INVALID, run python auth.py"
                        log.critical("FEED WATCHDOG: access token re-check "
                                     "FAILED - run `python auth.py`")
                        ticker.force_reconnect()
                    if not feed_down_flagged:
                        feed_down_flagged = True
                        bus.publish_feed({"feed_down": True,
                                          "feed_note": note})
                else:
                    ticker.force_reconnect()
                last_kick_mono = time_mod.monotonic()

            # the engine state; the fetch ran on a background thread)
            backfiller.poll(bar_writer)

            for tick in ticks:
                state = market.by_token.get(tick.get("instrument_token"))
                if state is None:
                    continue
                price = tick.get("last_price") or 0.0
                if price <= 0:
                    continue
                vol = tick.get("volume_traded") or 0
                oi = tick.get("oi") or 0
                if state.prev_close <= 0:
                    # FULL-mode ticks carry ohlc: open = today's real open,
                    # close = PREVIOUS day's close (the true day-% base)
                    ohlc = tick.get("ohlc")
                    if ohlc:
                        state.set_day_refs(ohlc.get("open") or 0.0,
                                           ohlc.get("close") or 0.0)
                ts = tick.get("exchange_timestamp") or datetime.now()
                minute = ts.replace(second=0, microsecond=0)
                oi_changed = state.on_tick(price, vol, oi, minute)
                if oi_changed:
                    # instant, intrabar spike check - the low-latency path
                    sig = detector.check(state, datetime.now(), intrabar=True)
                    if sig is not None:
                        signals_fired += 1
                        bus.publish_signal(sig)

            now = datetime.now()
            minute_end = pending_minute + timedelta(minutes=1,
                                                    seconds=CLOSE_GRACE_SECONDS)
            while now >= minute_end:
                closed = market.close_minute(pending_minute)
                if artifact_ranges:
                    # option bars in a gap's catch-up window carry the whole
                    # outage's OI change as one delta - mark them so flow
                    # windows skip them (futures get real backfilled bars)
                    for state, bar in closed:
                        if state.inst.kind != "FUT" \
                                and _in_artifact_range(bar.minute):
                            bar.artifact = True
                bar_writer.add_bars(closed)
                bar_ts = pending_minute + timedelta(minutes=1)
                for state, bar in closed:
                    if bar.volume <= 0 and bar.oi_delta == 0:
                        continue
                    sig = detector.check(state, bar_ts, intrabar=False)
                    if sig is not None:
                        signals_fired += 1
                        bus.publish_signal(sig)
                rows = ranker.compute(bar_ts)
                if rows:
                    bus.publish_ranking(rows)
                    builds = position_engine.compute(rows, bar_ts)
                    if builds or position_had:
                        bus.publish_position(builds)
                    position_had = bool(builds)
                    # radar first: feeds the one-way non-reverse entry path
                    radar_sigs = radar_engine.compute(bar_ts)
                    if radar_sigs or radar_had:
                        bus.publish_radar(radar_sigs)
                    radar_had = bool(radar_sigs)
                    movers = oneway_engine.compute(rows, bar_ts,
                                                   radar=radar_sigs,
                                                   near=radar_engine.near_flows)
                    if movers or oneway_had:
                        bus.publish_oneway(movers)
                    oneway_had = bool(movers)
                    oimult = oimult_engine.compute(bar_ts)
                    if oimult or oimult_had:
                        bus.publish_oimult(oimult)
                    oimult_had = bool(oimult)
                    # relative-strength leaders once at RSL_DECISION. Trades
                    rsl_picks = rs_leaders.maybe_lock(bar_ts)
                    if rsl_picks:
                        store.save_rs_leaders(rsl_picks)
                    sl_live = sector_leaders.compute(bar_ts)
                    if sl_live or sector_had:
                        bus.publish_sector(sl_live)
                    sector_had = bool(sl_live)
                    sl_board = sector_leaders.maybe_lock(bar_ts)
                    if sl_board:
                        store.save_sector_leaders(sl_board)
                if not day_refs_saved:
                    day_refs_saved = save_day_refs(market)
                pending_minute += timedelta(minutes=1)
                minute_end = pending_minute + timedelta(
                    minutes=1, seconds=CLOSE_GRACE_SECONDS)
            if tick_queue.dropped:
                log.warning("Tick queue dropped %d batches (backpressure)",
                            tick_queue.dropped)
    except KeyboardInterrupt:
        log.info("Interrupted by user - shutting down cleanly.")
    finally:
        ticker.stop()
        bar_writer.close()
        try:
            fut_minutes = max((s.bars_seen for s in
                               market.futures_by_underlying.values()),
                              default=0)
            if fut_minutes >= 200:
                save_flow_baseline(date.today(), oneway_engine, radar_engine)
            else:
                log.info("Flow baseline NOT saved (%d min of session data - "
                         "need 200+).", fut_minutes)
        except Exception:
            log.exception("flow baseline save failed")
        try:
            save_eod_oi_snapshot(market)
        except Exception:
            log.exception("EOD OI snapshot failed")
        try:
            store.finalize_day(date.today())
        except Exception:
            log.exception("EOD finalize failed")

    # ------------------------------------------------------ EOD summary ----
    print("\n================ END OF DAY SUMMARY ================")
    day_signals = store.signals_for_day(date.today())
    print(f"Signals fired today: {len(day_signals)}")
    top = sorted(day_signals, key=lambda s: s["score"], reverse=True)[:15]
    if top:
        print(f"\n{'Time':<10}{'Stock':<12}{'Contract':<24}{'Type':<16}"
              f"{'Side':<10}{'dOI%':>7}{'Rs cr':>8}{'Score':>7}")
        for s in top:
            contract = (s["tradingsymbol"] if s["kind"] == "FUT"
                        else f"{s['strike']:g}{s['kind']}")
            print(f"{s['ts'][11:19]:<10}{s['underlying']:<12}{contract:<24}"
                  f"{s['classification']:<16}{s['side'] or '-':<10}"
                  f"{s['oi_pct']:>7.1f}{s['notional_cr']:>8.1f}"
                  f"{s['score']:>7.0f}")
    print(f"\nRun `python replay.py --date {date.today().isoformat()}` for the full forward-return "
          "report.")
    store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live OI build-up screener")
    parser.add_argument("--now", action="store_true",
                        help="start immediately, do not wait for 09:15")
    parser.add_argument("--api", action="store_true",
                        help="also start the FastAPI dashboard server on port 8000")
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--no-warm", action="store_true",
                        help="skip warm-start (do NOT rebuild today's state "
                             "from recorded bars on a mid-day restart)")
    args = parser.parse_args()
    logging.basicConfig(level=config.LOG_LEVEL,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s",
                        datefmt="%H:%M:%S")
    if args.api:
        import uvicorn

        import api as api_module
        def _start_api(bus, store, universe_size):
            api_module.init(bus, store, universe_size)
            uvicorn.run(api_module.app, host="0.0.0.0", port=args.api_port,
                        log_level="warning")
        run(start_now=args.now, api_starter=_start_api,
            warm=not args.no_warm)
    else:
        run(start_now=args.now, warm=not args.no_warm)
