"""Central configuration: paths, market hours, thresholds, .env loader.

Thresholds for the one-way conviction funnel (OW_*, CONV_*, LOADER_*, NR_*,
SQZ_*, REGIME_*) are published as neutral reference defaults. The calibrated
production values are not part of this repository - see README, "What is not
in this repository".
"""
from __future__ import annotations

import os
from datetime import time
from pathlib import Path

# ---------------------------------------------------------------- paths ----
BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
STOCKS_FILE = BASE_DIR / "stocks.txt"

DATA_DIR = BASE_DIR / "data"
BARS_DIR = DATA_DIR / "bars"          # data/bars/{YYYY-MM-DD}/part_####.parquet
SIGNALS_DB = DATA_DIR / "signals" / "signals.sqlite"
META_DIR = DATA_DIR / "meta"          # instruments + universe snapshots

# -------------------------------------------------------------- market -----
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
SHUTDOWN_AT = time(15, 32)

# ------------------------------------------------------- kite limits -------
WS_MAX_PER_CONNECTION = 3000     # Kite hard limit per WebSocket connection
WS_MAX_CONNECTIONS = 3           # Kite hard limit per API key
UNIVERSE_CAPACITY = 8800         # safety margin below 3 x 3000
QUOTE_BATCH = 500                # REST /quote max instruments per call

# ------------------------------------------------------------ engine -------
OI_WINDOWS = (1, 3, 5, 15)       # rolling OI-delta windows, in minutes

BASELINE_BARS = 60
BASELINE_MIN_BARS = 15           # minimum history before z-scores are trusted
WARMUP_BARS = 15                 # no signals for the first N bars of the day
ZSCORE_CAP = 20.0                # clamp z when the baseline std is near zero
BAR_RING_SIZE = 400

# --------------------------------------------------- spike thresholds ------
SPIKE_ZSCORE_MIN = 3.0
SPIKE_OI_PCT_5M_OPT = 5.0        # 5-min OI change floor for options
SPIKE_OI_PCT_5M_FUT = 2.0        # 5-min OI change floor for futures
SPIKE_MIN_OI_LOTS = 10           # OI base must exceed 10 x lot_size contracts
SPIKE_COOLDOWN_MIN = 10          # per-instrument re-fire cooldown, minutes

SCORE_W_ZSCORE = 40.0            # composite spike score weights, clamped 0-100
SCORE_W_OI_PCT = 40.0
SCORE_W_VOLUME = 20.0

# -------------------------------------------------------- trade ideas ------
IDEA_MIN_FLOW_CR = 1.0           # ignore stocks below this 5-min option flow
IDEA_MIN_CONVICTION = 55.0       # emit ideas only above this conviction
IDEA_MAX_COUNT = 8

# -------------------------------------------- big-player momentum radar ----
MOM_WINDOW_START = time(9, 15)   # new picks admitted only inside this window
MOM_WINDOW_END = time(11, 0)
MOM_OI_MULT = 2.0                # build pace vs the contract's own average
MOM_MIN_DELTA_PCT = 2.0
MOM_BASELINE_BARS = 10
MOM_ATM_STRIKES = 3              # strikes scanned each side of spot
MOM_MIN_STRIKES = 2              # strikes that must agree
MOM_GROW_BARS = 6                # pace measured over this many minutes
MOM_GROW_MIN_UPS = 3
MOM_ONEWAY_RATIO = 0.6           # share of bars closing with the direction
MOM_ONEWAY_BARS = 15
MOM_MAX_PICKS = 5
MOM_IDEA_BOOST = 15.0            # conviction added when the radar agrees
MOM_EXIT_CONSEC = 3              # unwinding minutes before an exit alert
MOM_EXIT_GIVEBACK = 0.25
MOM_EXIT_BREAK_MIN = 20
MOM_NEAR_EXTREME_PCT = 0.5

# --------------------------------------------- early-entry money list ------
EARLY_MIN_FLOW_CR = 1.5
EARLY_MIN_DOMINANCE = 0.60       # one-sidedness of the option flow
EARLY_MAX_MOVE_15M = 0.6         # price must still be quiet
EARLY_MAX_MOVE_DAY = 2.5
EARLY_MIN_SCORE = 60.0
EARLY_EXIT_SCORE = 50.0          # hysteresis floor for an issued name
EARLY_MIN_STREAK = 2
EARLY_MAX_COUNT = 3
EARLY_WINDOW_START = time(10, 0)
EARLY_WINDOW_END = time(11, 0)
EARLY_STRIKES_SPAN = 10          # strikes searched for an opposing OI wall
EARLY_MIN_WALL_PCT = 0.75        # minimum runway to that wall
EARLY_MAX_VWAP_PCT = 0.8         # reject when stretched from session VWAP
EARLY_MIN_RVOL = 1.5             # relative volume floor

# ------------------------------------------------- best-of-day verdict -----
BEST_WINDOW_START = time(10, 0)
BEST_WINDOW_END = time(11, 15)
BEST_MIN_FLOW_CR = 1.0
BEST_MIN_DOMINANCE = 0.55
BEST_MIN_WALL_PCT = 0.4
BEST_MIN_DAY_ALIGN = 0.1
BEST_MIN_SCORE = 60.0
BEST_MIN_STREAK = 3
BEST_FAST_SCORE = 75.0           # skip the streak on very strong evidence
BEST_MAX_OPEN = 3
BEST_MAX_FROM_EXTREME = 0.5
BEST_MAX_OPEN_TREND = 6
BEST_BREADTH_MIN = 6
BEST_STRONG_DAY_PCT = 1.0
BEST_STRONG_DOMINANCE = 0.60
BEST_CONTRA_PENALTY = 8.0        # score penalty against a one-way tape
BEST_CHOP_PENALTY = 6.0
BEST_ROTATE_MARGIN = 10.0        # margin a new pick must beat an open one by
BEST_ROTATE_MAX_PNL = -0.2
BEST_MINORITY_MAX = 1
BEST_BREADTH_RATIO = 2.0
BEST_MIN_HOLD_MIN = 25
BEST_EXIT_WINDOW = 15
BEST_EXIT_MIN_CR = 1.5
BEST_EXIT_VWAP_MARGIN = 0.15
BEST_EXIT_DROUGHT_MIN = 25
BEST_TRAIL_ARM = 0.8             # move that arms the trail
BEST_TRAIL_KEEP = 0.5            # fraction of the peak move kept
BEST_STOP_PCT = 1.0
BEST_EOD_EXIT = time(14, 45)

# ---------------------------------------------------- position radar -------
POS_MIN_CUM_CR = 8.0
POS_MIN_DOM = 0.40
POS_BIG_CUM_CR = 60.0
POS_TOP_N = 8
POS_FLOW_FLOOR_CR = 0.5
POS_BUILD_FULL = 40.0
POS_LOADED_MAX_DAY = 0.4         # loaded but not yet moving
POS_MOVING_MIN_DAY = 0.8
POS_BURST_CR = 3.0
POS_BURST_CUM_CR = 10.0
POS_BURST_DOM = 0.55
POS_BREAK_LOOKBACK = 20

# ------------------------------------------ one-way momentum engine --------
# Reference defaults. Production values are not published.
OW_WINDOW_START = time(10, 0)    # fresh entries admitted in this window
OW_WINDOW_END = time(14, 30)
OW_MAX_PER_SIDE = 8              # concurrent open rides per direction
OW_DAILY_PER_SIDE = 12           # entries per direction per day
OW_MIN_BUILD_X = 6.0             # cum flow vs the stock's own typical flow
OW_RECENT_WIN = 15               # minutes in the recent-flow window
OW_MIN_RECENT_DOM = 0.55
OW_MIN_CLEAN = 0.55              # 1 - flow sign-flip rate
OW_EFF_WIN = 30                  # minutes for Kaufman price efficiency
OW_MIN_EFF = 0.25
OW_MAX_TWO_SIDED = 0.45          # min(bull, bear) / max(bull, bear) ceiling
OW_RETRACE_MAX = 0.40            # realized pullback / move so far
OW_MIN_MOVE = 0.3                # move needed before retracement is judged
OW_FLOW_FLOOR_CR = 0.5           # divide-by-tiny guard on typical flow
OW_BUILD_FULL = 40.0             # build_x at which the score factor saturates
OW_MAX_FROM_EXTREME = 0.6        # distance allowed from the session extreme
OW_MIN_SCORE = 60.0
OW_MIN_STREAK = 3                # qualifying minutes before entry

OW_FAST_WINDOW_START = time(9, 20)
OW_FAST_SURGE_X = 4.0            # recent flow vs the stock's normal rate
OW_FAST_MIN_DOM = 0.65
OW_FAST_MIN_EFF = 0.50
OW_FAST_STREAK = 2
OW_BASELINE_MIN = 20             # minutes before session typical flow is used

OW_ROTATE_MARGIN = 8.0
OW_ROTATE_MAX_PNL = -0.1
OW_EXIT_FLIP_MIN = 2
OW_EXIT_TWO_SIDED_MIN = 3
OW_EXIT_RETRACE = 0.4
OW_STOP_PCT = 1.0                # hard safety stop, percent against entry
OW_MIN_HOLD_MIN = 10
OW_EOD_EXIT = time(15, 0)

# --------------------- day-regime meter + ride exit ------------------------
REGIME_ACTIVE_MOVE = 0.8         # peak move that makes a stock "active"
REGIME_CLEAN_RETR = 0.35
REGIME_FADE_RETR = 0.55
REGIME_TREND_RATIO = 0.90        # clean / faded ratio for TREND
REGIME_CHOP_RATIO = 0.60
REGIME_MIN_ACTIVE = 8            # active names before the ratio is trusted
REGIME_GAP_MIN = 0.30
REGIME_GAP_KEEP = 0.50
REGIME_GAP_CONVICTION = 30
REGIME_GAPHOLD_TREND = 0.60      # gap-hold breadth for a TREND open
REGIME_GAPHOLD_CHOP = 0.45
REGIME_LATE_START = time(9, 20)
REGIME_BUDGET = {"TREND": 12, "MIXED": 6, "CHOP": 3}     # entries / side / day
REGIME_SIZE = {"TREND": 1.0, "MIXED": 0.6, "CHOP": 0.3}  # advisory size mult
REGIME_STOP = {"TREND": 1.0, "MIXED": 0.6, "CHOP": 0.45}  # hard stop percent
REGIME_STRUCTURAL = {"nr", "squeeze"}   # kinds admitted on a CHOP day

OW_RIDE_TRAIL = 0.55             # exit once pnl falls below this x peak move
OW_RIDE_MIN_PEAK = 0.5           # ... and only after the move exceeded this

# ------------------------------------------ big player radar (near-spot) ---
RADAR_ATM_STRIKES = 10           # strikes each side of spot counted as "near"
RADAR_WINDOW = 5
RADAR_MIN_FLOW_CR = 1.0
RADAR_MIN_DOM = 0.55
RADAR_TOP_N = 8

# ------------------- non-reverse "point of no return" entry path (NR_*) ----
NR_WATCH_MIN_SCANS = 3           # radar minutes, same direction, to arm
NR_WATCH_RECENT = 10
NR_MIN_LEG_PCT = 0.8             # minimum break leg, swing to extreme
NR_RETRACE_MAX = 0.40            # fraction of the leg a retest may give back
NR_PULLBACK_MIN_PCT = 0.10       # a real pullback off the extreme
NR_PULLBACK_MIN_AGE = 2
NR_RECLAIM_VWAP_MIN = 3
NR_MIN_DAY_PCT = 1.0
NR_EARLIEST = time(10, 0)
NR_LATEST = time(14, 0)
NR_STOP_BUFFER_PCT = 0.35        # structural stop = retest level +/- this

# ------------------------------------------- feed watchdog -----------------
FEED_STALE_SECONDS = 25          # no ticks for this long triggers a reconnect
FEED_RECONNECT_MAX = 3           # forced reconnects before a token re-check

# ------------------------------------- zero-data-loss / backfill -----------
BACKFILL_RATE_SLEEP = 0.35       # Kite historical REST is ~3 req/s
BACKFILL_MIN_GAP_MIN = 3         # gaps shorter than this are not backfilled
ARTIFACT_PAD_MIN = 1             # minutes after a gap flagged as artifact

# ----------------------------------- cross-day flow baselines --------------
FLOW_BASELINE_FILE = META_DIR / "flow_baseline.csv"
BASELINE_TRAIL_DAYS = 10         # trailing days kept in the baseline file
BASELINE_MIN_SAMPLES = 30        # minutes a stock needs to contribute a day

# ----------------------------------- opening-loader entry path -------------
LOADER_EARLIEST = time(9, 25)
LOADER_LATEST = time(10, 30)
LOADER_WIN = 10                  # rolling near-spot flow window, minutes
LOADER_SURGE_X = 4.0             # vs the stock's own prior-day near-spot scale
LOADER_MIN_DOM = 0.70
LOADER_ABS_NET_CR = 25.0         # absolute branch for stocks with no baseline
LOADER_ABS_MIN_DOM = 0.75
LOADER_MIN_DAY_PCT = 0.4
LOADER_MAX_EXT_PCT = 0.4         # distance allowed from the session extreme
LOADER_CONSEC = 4                # consecutive qualifying minutes to flag

NR_RETRACE_MAX_OPEN = 0.5        # opening structures pull back deeper
NR_OPEN_UNTIL = time(10, 30)
NR_EARLY_DAY_PCT = 0.4

# -------------- squeeze rider ----------------------------------------------
SQZ_WIN = 30                     # rolling flow window, minutes
SQZ_MIN_HIST = 10
SQZ_FORCED_MIN = 0.60            # forced share of the aligned flow
SQZ_SURGE_X = 2.0
SQZ_MIN_DAY_PCT = 0.4
SQZ_CONSEC = 3
SQZ_START = time(9, 45)
SQZ_END = time(13, 30)
SQZ_MAX_PER_SIDE = 3
SQZ_PRIME_END = time(11, 30)

# --------------------------------- pullback-as-accumulation ----------------
OW_ACCUM_DOM = 0.60

# --------------------------------------- breadth guard ---------------------
OW_BREADTH_MIN = 6               # qualifiers needed to call the tape one-way
OW_BREADTH_RATIO = 2.0
OW_MINORITY_MAX = 2              # open calls allowed against a one-way tape

# ------------------ the conviction funnel ----------------------------------
OW_BADGE_PRIME_END = time(10, 20)
CONV_MIN_SURVIVED_MIN = 30       # leg 1: minutes since entry with no stop hit
CONV_FRESH_EXT_WIN = 15          # leg 2: fresh post-entry extreme window
CONV_FLOW_MIN_CR = 0.0           # leg 3: cum aligned flow floor since entry
CONV_MIN_PNL = 1.0               # leg 4: ride P&L at the promotion minute
CONV_STALL_MIN = 20              # promoted with no fresh extreme -> STALLING
CONV_ALLOW_NORMAL = True         # let normal/fast kinds promote too
CONV_PRIME_TREND_LATEST = time(11, 30)   # TREND-day eligibility extension

# ----------------------------- relative-strength leaders (shadow) ----------
RSL_DECISION = time(10, 15)
RSL_TOP_N = 2
RSL_RS_FLOOR = 1.0
RSL_MIN_MOVE = 0.5
RSL_MAX_RETR = 0.35

# --------------------------------------- sector leaders (shadow) -----------
SL_DECISION = time(10, 45)
SL_TOP_SECTORS = 6
SL_LEADERS_PER_SECTOR = 2
SL_MIN_SECTOR_MEMBERS = 3
SL_MIN_LEAD_MOVE = 1.0
SL_SECTOR_STRENGTH_N = 2
SL_BREAKOUT_MOVE = 1.0

FUEL_WIN = 30                    # rolling window for the forced/spec split

# -------------------- OI build-up multiple ranking board -------------------
OIM_BASE_CUTOFF = time(9, 30)    # bars up to here form the day's OI base
OIM_NEAR_STEPS = 10
OIM_MIN_BASE = 5_000             # ignore contracts with a tiny OI base
OIM_FRESH_MIN = 50_000           # fresh OI floor for a row to count
OIM_CHECKPOINT = 2.0             # OI multiple that marks a checkpoint
OIM_MIN_DOM = 0.60
OIM_TOP_N = 12
OIM_MIXED_N = 6
OIM_TAPE_MIN = 20
OIM_TAPE_RATIO = 2.0

# ------------------------------------------------------------ storage ------
BARS_FLUSH_SECONDS = 30          # bar-writer flush interval, zero data loss

# ------------------------------------------------------------- misc --------
LOG_LEVEL = os.environ.get("OI_LOG_LEVEL", "INFO")


def load_env(path: Path = ENV_FILE) -> dict[str, str]:
    """Tiny stdlib .env parser (KEY=VALUE lines, # comments)."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def save_env_value(key: str, value: str, path: Path = ENV_FILE) -> None:
    """Update or append one KEY=VALUE in the .env file, preserving the rest."""
    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    replaced = False
    for i, line in enumerate(lines):
        if line.split("=", 1)[0].strip() == key:
            lines[i] = f"{key}={value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_stock_list(path: Path = STOCKS_FILE) -> list[str]:
    """Read the F&O underlying symbols to monitor, one per line."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found - create it with one NSE F&O symbol per line."
        )
    symbols: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        sym = line.strip().upper()
        if sym and not sym.startswith("#"):
            symbols.append(sym)
    return symbols


def ensure_dirs() -> None:
    for d in (BARS_DIR, SIGNALS_DB.parent, META_DIR):
        d.mkdir(parents=True, exist_ok=True)
