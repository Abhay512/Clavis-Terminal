"""Persistence: Parquet bar writer plus a SQLite store for every board."""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
from datetime import date, datetime

import pyarrow as pa
import pyarrow.parquet as pq

import config
from engine.bar_builder import Bar
from engine.big_player_radar import BigPlayerSignal
from engine.market_state import InstrumentState, MarketState
from engine.oi_multiple import OIMultipleRow
from engine.oneway_momentum import OneWayMover
from engine.position_radar import PositionBuild
from engine.ranking import StockRank
from engine.spike_detector import Signal

log = logging.getLogger("storage")


def save_day_refs(market: MarketState) -> bool:
    """Persist per-token day references (prev close, exchange open) from live ticks."""
    futs = list(market.futures_by_underlying.values())
    have = [s for s in market.by_token.values() if s.prev_close > 0]
    futs_have = sum(1 for s in futs if s.prev_close > 0)
    if not futs or futs_have < 0.8 * len(futs):
        return False
    path = config.META_DIR / f"{date.today().isoformat()}_dayrefs.csv"
    lines = ["token,prev_close,exch_open"]
    lines += [f"{s.inst.token},{s.prev_close},{s.exch_open}" for s in have]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("Saved day refs for %d instruments -> %s", len(have), path.name)
    return True


def save_eod_oi_snapshot(market: MarketState, day: date | None = None) -> int:
    """Compact per-instrument EOD OI snapshot, one file per session."""
    day = day or date.today()
    lines = ["underlying,kind,strike,expiry,oi_close,last_price,"
             "fut_close,day_pct"]
    n = 0
    for s in market.by_token.values():
        if s.last_price <= 0 and s.last_oi <= 0:
            continue
        fut = market.futures_by_underlying.get(s.inst.underlying)
        fut_close = fut.last_price if fut is not None else 0.0
        day_pct = fut.day_pct() if fut is not None else 0.0
        lines.append(f"{s.inst.underlying},{s.inst.kind},{s.inst.strike:g},"
                     f"{s.inst.expiry},{s.last_oi},{s.last_price},"
                     f"{fut_close},{day_pct:.2f}")
        n += 1
    if n == 0:
        return 0
    path = config.META_DIR / f"{day.isoformat()}_eod_oi.csv"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("EOD OI snapshot: %d instruments -> %s", n, path.name)
    return n


def load_day_refs(market: MarketState, day: date) -> int:
    path = config.META_DIR / f"{day.isoformat()}_dayrefs.csv"
    if not path.exists():
        return 0
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.split(",")
        if len(parts) != 3:
            continue
        state = market.by_token.get(int(parts[0]))
        if state is not None:
            state.set_day_refs(float(parts[2]), float(parts[1]))
            n += 1
    return n

BAR_SCHEMA = pa.schema([
    ("minute", pa.timestamp("s")),
    ("token", pa.int64()),
    ("tradingsymbol", pa.string()),
    ("underlying", pa.string()),
    ("kind", pa.string()),
    ("strike", pa.float64()),
    ("open", pa.float64()),
    ("high", pa.float64()),
    ("low", pa.float64()),
    ("close", pa.float64()),
    ("volume", pa.int64()),
    ("oi", pa.int64()),
    ("oi_delta", pa.int64()),
    ("backfilled", pa.int8()),
])


class BarWriter:
    """Buffered, thread-safe Parquet writer for 1-min bars."""

    def __init__(self, session_date: date | None = None):
        config.ensure_dirs()
        self.dir = config.BARS_DIR / (session_date or date.today()).isoformat()
        self.dir.mkdir(parents=True, exist_ok=True)
        self._buffer: list[tuple] = []
        self._lock = threading.Lock()
        self._part = self._next_part_index()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _next_part_index(self) -> int:
        existing = sorted(self.dir.glob("part_*.parquet"))
        if not existing:
            return 0
        return int(existing[-1].stem.split("_")[1]) + 1

    def add_bars(self, closed: list[tuple[InstrumentState, Bar]]) -> None:
        rows = []
        for state, bar in closed:
            i = state.inst
            rows.append((bar.minute, i.token, i.tradingsymbol, i.underlying,
                         i.kind, i.strike, bar.open, bar.high, bar.low,
                         bar.close, bar.volume, bar.oi, bar.oi_delta,
                         2 if bar.artifact else 0))
        with self._lock:
            self._buffer.extend(rows)

    def add_backfill(self, rows: list[tuple]) -> None:
        """Rows fetched from kite.historical_data after a feed gap
        (already in BAR_SCHEMA order with backfilled=1)."""
        with self._lock:
            self._buffer.extend(rows)

    def flush(self) -> int:
        with self._lock:
            rows, self._buffer = self._buffer, []
        if not rows:
            return 0
        cols = list(zip(*rows))
        table = pa.table(
            {f.name: list(col) for f, col in zip(BAR_SCHEMA, cols)},
            schema=BAR_SCHEMA)
        path = self.dir / f"part_{self._part:04d}.parquet"
        with open(path, "wb") as f:
            pq.write_table(table, f, compression="snappy")
            f.flush()
            os.fsync(f.fileno())
        self._part += 1
        log.debug("Flushed %d bar rows -> %s", len(rows), path.name)
        return len(rows)

    def start_background(self) -> None:
        def loop():
            while not self._stop.wait(config.BARS_FLUSH_SECONDS):
                try:
                    self.flush()
                except Exception:
                    log.exception("bar flush failed")
        self._thread = threading.Thread(target=loop, name="bar-writer",
                                        daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        self.flush()


class SignalStore:
    """SQLite store for fired signals and per-minute stock rankings."""

    def __init__(self):
        config.ensure_dirs()
        self._conn = sqlite3.connect(config.SIGNALS_DB,
                                     check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.execute("PRAGMA journal_mode=WAL")
        # corrupt the db (the zero-data-loss invariant #2)
        self._conn.execute("PRAGMA synchronous=NORMAL")
        try:
            res = self._conn.execute("PRAGMA quick_check").fetchone()[0]
            if res == "ok":
                log.info("SQLite quick_check: ok (%s)", config.SIGNALS_DB.name)
            else:
                log.error("SQLite quick_check FAILED: %s - the signals db "
                          "may be corrupt, back it up and investigate", res)
        except Exception:
            log.exception("SQLite quick_check errored")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS feed_gaps (
                day TEXT, start_ts TEXT, end_ts TEXT, recovered_by TEXT
            )""")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                ts TEXT, token INTEGER, tradingsymbol TEXT, underlying TEXT,
                kind TEXT, strike REAL, expiry TEXT, window INTEGER,
                oi_now INTEGER, oi_delta INTEGER, oi_pct REAL, zscore REAL,
                price REAL, price_pct REAL, volume INTEGER,
                classification TEXT, side TEXT, underlying_price REAL,
                notional_cr REAL, score REAL, intrabar INTEGER
            )""")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS rankings (
                ts TEXT, underlying TEXT, fut_price REAL,
                fut_classification TEXT, buy_units INTEGER,
                sell_units INTEGER, buy_notional_cr REAL,
                sell_notional_cr REAL, top_buy_strike TEXT,
                top_sell_strike TEXT
            )""")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS trade_ideas (
                ts TEXT, underlying TEXT, direction TEXT, conviction REAL,
                fut_price REAL, price_pct_day REAL, price_pct_15m REAL,
                bull_flow_cr REAL, bear_flow_cr REAL, net_flow_cr REAL,
                suggested_contract TEXT, reasons TEXT
            )""")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS momentum_picks (
                ts TEXT, underlying TEXT, direction TEXT, status TEXT,
                score REAL, streak_min INTEGER, entered TEXT,
                fut_price REAL, price_pct_day REAL, oi_mult REAL,
                strikes_confirmed INTEGER, strikes_total INTEGER,
                all_strikes INTEGER, watch_contract TEXT, note TEXT
            )""")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS early_entries (
                ts TEXT, underlying TEXT, direction TEXT, score REAL,
                streak_min INTEGER, fut_price REAL, price_pct_day REAL,
                price_pct_15m REAL, net_flow_cr REAL, dominance REAL,
                flow_accel_cr REAL, writer_cr REAL, radar INTEGER,
                vwap_pct REAL, wall_pct REAL, rvol REAL,
                suggested_contract TEXT, reasons TEXT
            )""")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS best_picks (
                ts TEXT, underlying TEXT, direction TEXT, status TEXT,
                score REAL, entry_ts TEXT, entry_price REAL,
                last_price REAL, pnl_pct REAL, bull_cr REAL, bear_cr REAL,
                build_cr REAL, exit_cr REAL, contract TEXT,
                reasons TEXT, note TEXT
            )""")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS position_builds (
                ts TEXT, underlying TEXT, direction TEXT, phase TEXT,
                score REAL, cum_net_cr REAL, cum_total_cr REAL,
                dominance REAL, persistence REAL, fut_price REAL,
                price_pct_day REAL, first_seen TEXT, breakout_ts TEXT,
                monitored_min INTEGER, ce_wall TEXT, pe_wall TEXT, note TEXT
            )""")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS big_player_radar (
                ts TEXT, underlying TEXT, direction TEXT, strength REAL,
                near_dom REAL, net_cr REAL, fut_price REAL,
                price_pct_day REAL, ce_strike TEXT, pe_strike TEXT,
                n_strikes INTEGER, first_seen TEXT, monitored_min INTEGER,
                note TEXT
            )""")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS oi_multiple_board (
                ts TEXT, underlying TEXT, running_max REAL, contract TEXT,
                base_oi INTEGER, peak_oi INTEGER, t_max TEXT, first_2x TEXT,
                strikes_2x INTEGER, direction TEXT, dominance REAL,
                bull_cr REAL, bear_cr REAL, top_writer INTEGER, fresh TEXT,
                fut_price REAL, price_pct_day REAL, monitored_min INTEGER,
                counter_tape INTEGER DEFAULT 0
            )""")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS oneway_movers (
                ts TEXT, underlying TEXT, direction TEXT, status TEXT,
                score REAL, entry_ts TEXT, entry_price REAL, last_price REAL,
                pnl_pct REAL, price_pct_day REAL, build_x REAL,
                dominance REAL, clean_flow REAL, retrace_pct REAL,
                two_sided REAL, cum_net_cr REAL, monitored_min INTEGER,
                contract TEXT, note TEXT, reasons TEXT
            )""")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS rs_leaders (
                ts TEXT, underlying TEXT, direction TEXT, rs REAL,
                ret_pct REAL, basket_pct REAL, retrace REAL, rank INTEGER,
                fut_price REAL, locked INTEGER DEFAULT 0
            )""")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sector_leaders (
                ts TEXT, sector TEXT, sector_strength REAL, sector_rank INTEGER,
                underlying TEXT, direction TEXT, move_pct REAL,
                rank_in_sector INTEGER, fut_price REAL, breakout_ts TEXT,
                locked INTEGER DEFAULT 0
            )""")
        self._migrate_rankings()
        self._migrate_early()
        self._migrate_2026_07_07()
        self._migrate_2026_07_12()
        self._migrate_2026_07_14()
        self._migrate_oimult()
        self._migrate_regime()
        self._migrate_stop_fuel()
        self._migrate_sector_leaders()
        self._conn.commit()

    def _migrate_sector_leaders(self) -> None:
        """Add breakout_ts to an existing sector_leaders table."""
        existing = {row[1] for row in
                    self._conn.execute("PRAGMA table_info(sector_leaders)")}
        if "breakout_ts" not in existing:
            self._conn.execute(
                "ALTER TABLE sector_leaders ADD COLUMN breakout_ts TEXT")

    def _migrate_rankings(self) -> None:
        """Add columns introduced after the table was first created."""
        existing = {row[1] for row in
                    self._conn.execute("PRAGMA table_info(rankings)")}
        new_cols = {
            "price_pct_day": "REAL DEFAULT 0",
            "ce_buy_cr": "REAL DEFAULT 0",
            "pe_buy_cr": "REAL DEFAULT 0",
            "ce_write_cr": "REAL DEFAULT 0",
            "pe_write_cr": "REAL DEFAULT 0",
            "top_ce_buy_strike": "TEXT DEFAULT ''",
            "top_pe_buy_strike": "TEXT DEFAULT ''",
            "ce_cover_cr": "REAL DEFAULT 0",
            "pe_cover_cr": "REAL DEFAULT 0",
            "ce_unwind_cr": "REAL DEFAULT 0",
            "pe_unwind_cr": "REAL DEFAULT 0",
        }
        for col, decl in new_cols.items():
            if col not in existing:
                self._conn.execute(
                    f"ALTER TABLE rankings ADD COLUMN {col} {decl}")

    def _migrate_early(self) -> None:
        existing = {row[1] for row in
                    self._conn.execute("PRAGMA table_info(early_entries)")}
        for col in ("vwap_pct", "wall_pct", "rvol"):
            if col not in existing:
                self._conn.execute(
                    f"ALTER TABLE early_entries ADD COLUMN {col} "
                    f"REAL DEFAULT 0")

    def _migrate_2026_07_07(self) -> None:
        """monitored_min everywhere + radar breakout/exit timestamps."""
        adds = {
            "signals": {"monitored_min": "INTEGER DEFAULT 0"},
            "trade_ideas": {"monitored_min": "INTEGER DEFAULT 0"},
            "early_entries": {"monitored_min": "INTEGER DEFAULT 0"},
            "best_picks": {"monitored_min": "INTEGER DEFAULT 0"},
            "momentum_picks": {"monitored_min": "INTEGER DEFAULT 0",
                               "breakout_ts": "TEXT DEFAULT ''",
                               "exit_ts": "TEXT DEFAULT ''"},
        }
        for table, cols in adds.items():
            existing = {row[1] for row in
                        self._conn.execute(f"PRAGMA table_info({table})")}
            for col, decl in cols.items():
                if col not in existing:
                    self._conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN {col} {decl}")

    def _migrate_2026_07_12(self) -> None:
        """One-Way v2: entry-path kind (normal|fast|nr|loader) on movers."""
        existing = {row[1] for row in
                    self._conn.execute("PRAGMA table_info(oneway_movers)")}
        if "kind" not in existing:
            self._conn.execute(
                "ALTER TABLE oneway_movers ADD COLUMN kind TEXT DEFAULT ''")

    def _migrate_2026_07_14(self) -> None:
        """Add promotion and prime-window state to oneway_movers."""
        existing = {row[1] for row in
                    self._conn.execute("PRAGMA table_info(oneway_movers)")}
        new_cols = {
            "conviction": "INTEGER DEFAULT 0",
            "conv_ts": "TEXT DEFAULT ''",
            "prime_window": "INTEGER DEFAULT 1",
            "stalling": "INTEGER DEFAULT 0",
            "forced_share": "REAL DEFAULT 0",
        }
        for col, decl in new_cols.items():
            if col not in existing:
                self._conn.execute(
                    f"ALTER TABLE oneway_movers ADD COLUMN {col} {decl}")

    def _migrate_regime(self) -> None:
        """Add the ride's day regime and advisory size multiplier."""
        existing = {row[1] for row in
                    self._conn.execute("PRAGMA table_info(oneway_movers)")}
        new_cols = {
            "regime": "TEXT DEFAULT 'MIXED'",
            "size": "REAL DEFAULT 1.0",
        }
        for col, decl in new_cols.items():
            if col not in existing:
                self._conn.execute(
                    f"ALTER TABLE oneway_movers ADD COLUMN {col} {decl}")

    def _migrate_stop_fuel(self) -> None:
        """Persist stop_px and the fuel decomposition alongside each ride."""
        existing = {row[1] for row in
                    self._conn.execute("PRAGMA table_info(oneway_movers)")}
        new_cols = {
            "stop_px": "REAL DEFAULT 0",
            "fuel_forced_cr": "REAL DEFAULT 0",
            "fuel_spec_cr": "REAL DEFAULT 0",
        }
        for col, decl in new_cols.items():
            if col not in existing:
                self._conn.execute(
                    f"ALTER TABLE oneway_movers ADD COLUMN {col} {decl}")

    def _migrate_oimult(self) -> None:
        """Add counter_tape to an existing oi_multiple_board table."""
        existing = {row[1] for row in
                    self._conn.execute("PRAGMA table_info(oi_multiple_board)")}
        if existing and "counter_tape" not in existing:
            self._conn.execute("ALTER TABLE oi_multiple_board "
                               "ADD COLUMN counter_tape INTEGER DEFAULT 0")

    # ------------------------------------------------------------ feed gaps --
    def save_feed_gap(self, start: datetime, end: datetime,
                      recovered_by: str) -> None:
        """Record a feed outage window so replays / evals know which minutes
        are artifact instead of hardcoding them (the 07-10 lesson)."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO feed_gaps VALUES (?,?,?,?)",
                (start.date().isoformat(), start.isoformat(),
                 end.isoformat(), recovered_by))
            self._conn.commit()
        log.warning("Feed gap recorded: %s -> %s (%s)",
                    start.strftime("%H:%M:%S"), end.strftime("%H:%M:%S"),
                    recovered_by)

    def feed_gaps_for_day(self, day: date) -> list[dict]:
        cur = self._conn.execute(
            "SELECT start_ts, end_ts, recovered_by FROM feed_gaps "
            "WHERE day = ? ORDER BY start_ts", (day.isoformat(),))
        return [{"start_ts": r[0], "end_ts": r[1], "recovered_by": r[2]}
                for r in cur.fetchall()]

    def save_signal(self, s: Signal) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO signals
                   (ts, token, tradingsymbol, underlying, kind, strike,
                    expiry, window, oi_now, oi_delta, oi_pct, zscore, price,
                    price_pct, volume, classification, side,
                    underlying_price, notional_cr, score, intrabar,
                    monitored_min)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (s.ts.isoformat(), s.token, s.tradingsymbol, s.underlying,
                 s.kind, s.strike, s.expiry, s.window, s.oi_now, s.oi_delta,
                 s.oi_pct, s.zscore, s.price, s.price_pct, s.volume,
                 s.classification, s.side, s.underlying_price,
                 s.notional_cr, s.score, int(s.intrabar), s.monitored_min))
            self._conn.commit()

    def save_rankings(self, rows: list[StockRank]) -> None:
        if not rows:
            return
        with self._lock:
            self._conn.executemany(
                """INSERT INTO rankings
                   (ts, underlying, fut_price, fut_classification,
                    buy_units, sell_units, buy_notional_cr, sell_notional_cr,
                    top_buy_strike, top_sell_strike, price_pct_day,
                    ce_buy_cr, pe_buy_cr, ce_write_cr, pe_write_cr,
                    top_ce_buy_strike, top_pe_buy_strike,
                    ce_cover_cr, pe_cover_cr, ce_unwind_cr, pe_unwind_cr)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [(r.ts.isoformat(), r.underlying, r.fut_price,
                  r.fut_classification, r.buy_units, r.sell_units,
                  r.buy_notional_cr, r.sell_notional_cr,
                  r.top_buy_strike, r.top_sell_strike, r.price_pct_day,
                  r.ce_buy_cr, r.pe_buy_cr, r.ce_write_cr, r.pe_write_cr,
                  r.top_ce_buy_strike, r.top_pe_buy_strike,
                  r.ce_cover_cr, r.pe_cover_cr, r.ce_unwind_cr,
                  r.pe_unwind_cr) for r in rows])
            self._conn.commit()

    def save_position(self, builds: list[PositionBuild]) -> None:
        if not builds:
            return
        with self._lock:
            self._conn.executemany(
                "INSERT INTO position_builds VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(b.ts.isoformat(), b.underlying, b.direction, b.phase,
                  b.score, b.cum_net_cr, b.cum_total_cr, b.dominance,
                  b.persistence, b.fut_price, b.price_pct_day,
                  b.first_seen.isoformat(),
                  b.breakout_ts.isoformat() if b.breakout_ts else "",
                  b.monitored_min, b.ce_wall, b.pe_wall, b.note)
                 for b in builds])
            self._conn.commit()

    def save_radar(self, sigs: list[BigPlayerSignal]) -> None:
        if not sigs:
            return
        with self._lock:
            self._conn.executemany(
                "INSERT INTO big_player_radar VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(s.ts.isoformat(), s.underlying, s.direction, s.strength,
                  s.near_dom, s.net_cr, s.fut_price, s.price_pct_day,
                  s.ce_strike, s.pe_strike, s.n_strikes,
                  s.first_seen.isoformat(), s.monitored_min, s.note)
                 for s in sigs])
            self._conn.commit()

    def save_rs_leaders(self, rows) -> None:
        """Shadow record of the day's relative-strength leaders (no trading)."""
        if not rows:
            return
        with self._lock:
            self._conn.executemany(
                """INSERT INTO rs_leaders
                   (ts, underlying, direction, rs, ret_pct, basket_pct,
                    retrace, rank, fut_price, locked)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                [(r.ts.isoformat(), r.underlying, r.direction, r.rs,
                  r.ret_pct, r.basket_pct, r.retrace, r.rank, r.fut_price,
                  int(r.locked)) for r in rows])
            self._conn.commit()

    def save_sector_leaders(self, rows) -> None:
        """Shadow record of the day's sector-leader board (no trading)."""
        if not rows:
            return
        with self._lock:
            self._conn.executemany(
                """INSERT INTO sector_leaders
                   (ts, sector, sector_strength, sector_rank, underlying,
                    direction, move_pct, rank_in_sector, fut_price, breakout_ts,
                    locked)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                [(r.ts.isoformat(), r.sector, r.sector_strength, r.sector_rank,
                  r.underlying, r.direction, r.move_pct, r.rank_in_sector,
                  r.fut_price,
                  r.breakout_ts.isoformat() if r.breakout_ts else None,
                  int(r.locked)) for r in rows])
            self._conn.commit()

    def save_oneway(self, movers: list[OneWayMover]) -> None:
        if not movers:
            return
        with self._lock:
            self._conn.executemany(
                """INSERT INTO oneway_movers
                   (ts, underlying, direction, status, score, entry_ts,
                    entry_price, last_price, pnl_pct, price_pct_day, build_x,
                    dominance, clean_flow, retrace_pct, two_sided, cum_net_cr,
                    monitored_min, contract, note, reasons, kind,
                    conviction, conv_ts, prime_window, stalling, forced_share,
                    regime, size, stop_px, fuel_forced_cr, fuel_spec_cr)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                           ?,?,?,?,?,?,?,?,?,?)""",
                [(m.ts.isoformat(), m.underlying, m.direction, m.status,
                  m.score, m.entry_ts.isoformat(), m.entry_price,
                  m.last_price, m.pnl_pct, m.price_pct_day, m.build_x,
                  m.dominance, m.clean_flow, m.retrace_pct, m.two_sided,
                  m.cum_net_cr, m.monitored_min, m.contract, m.note,
                  "; ".join(m.reasons), m.kind,
                  int(m.conviction),
                  m.conv_ts.isoformat() if m.conv_ts else "",
                  int(m.prime_window), int(m.stalling),
                  m.forced_share, m.regime, m.size,
                  m.stop_px, m.fuel_forced_cr, m.fuel_spec_cr)
                 for m in movers])
            self._conn.commit()

    def save_oimult(self, rows: list[OIMultipleRow]) -> None:
        if not rows:
            return
        with self._lock:
            self._conn.executemany(
                "INSERT INTO oi_multiple_board "
                "(ts, underlying, running_max, contract, base_oi, peak_oi, "
                "t_max, first_2x, strikes_2x, direction, dominance, bull_cr, "
                "bear_cr, top_writer, fresh, fut_price, price_pct_day, "
                "monitored_min, counter_tape) VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(r.ts.isoformat(), r.underlying, r.running_max, r.contract,
                  r.base_oi, r.peak_oi, r.t_max.isoformat(),
                  r.first_2x.isoformat() if r.first_2x else "",
                  r.strikes_2x, r.direction, r.dominance, r.bull_cr,
                  r.bear_cr, int(r.top_writer), r.fresh, r.fut_price,
                  r.price_pct_day, r.monitored_min,
                  int(r.counter_tape)) for r in rows])
            self._conn.commit()

    def signals_for_day(self, day: date) -> list[dict]:
        cur = self._conn.execute(
            "SELECT * FROM signals WHERE ts LIKE ? ORDER BY ts",
            (f"{day.isoformat()}%",))
        names = [d[0] for d in cur.description]
        return [dict(zip(names, row)) for row in cur.fetchall()]

    # --------------------------------------------------------- EOD finalizer --
    DAY_TABLES = ("signals", "rankings", "position_builds",
                  "big_player_radar", "oneway_movers", "oi_multiple_board",
                  "feed_gaps")

    def finalize_day(self, day: date) -> dict[str, int]:
        """The 'nothing missing' receipt: per-table row counts for the day,
        then ANALYZE + optimize + vacuum. Runs at EOD and on clean shutdown."""
        counts: dict[str, int] = {}
        with self._lock:
            self._conn.commit()
            for table in self.DAY_TABLES:
                ts_col = "start_ts" if table == "feed_gaps" else "ts"
                try:
                    counts[table] = self._conn.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE {ts_col} LIKE ?",
                        (f"{day.isoformat()}%",)).fetchone()[0]
                except sqlite3.Error:
                    counts[table] = -1
            try:
                self._conn.execute("ANALYZE")
                self._conn.execute("PRAGMA optimize")
                self._conn.commit()
                self._conn.execute("VACUUM")
            except sqlite3.Error:
                log.exception("EOD vacuum/analyze failed (data unaffected)")
        log.info("EOD receipt %s: %s", day.isoformat(),
                 "  ".join(f"{t}={n}" for t, n in counts.items()))
        return counts

    def close(self) -> None:
        with self._lock:
            self._conn.commit()
            self._conn.close()
