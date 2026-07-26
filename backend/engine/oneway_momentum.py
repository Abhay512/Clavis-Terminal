"""Reference implementation of the one-way momentum board.

The production engine that runs this desk is not part of this repository.
What ships here is a smaller, self-contained model with the same public
surface (OneWayMover, OneWayMomentum.compute) and the same shape of output,
so every downstream consumer - signal bus, SQLite store, REST/WebSocket API
and the dashboard - can be run, read and extended end to end.

The reference scorer ranks a stock on four live-computable properties:

    build_x    cumulative net option flow / the stock's own typical flow
    dominance  one-sidedness of that flow over a rolling window
    clean_flow 1 - the rate at which net flow changes sign
    oneway     how little price has retraced against the move so far

    score = 100 * magnitude(build_x) * dominance * clean_flow * oneway

A stock enters once the score holds above a floor for a few minutes inside
the entry window, subject to per-side and per-day budgets. Open rides are
managed with a hard stop, a give-back trail and a forced close before the
bell. A ride that survives, prints a fresh extreme, keeps its flow aligned
and reaches a P&L floor is promoted to the top board.

Deliberately not modelled here: the alternative entry paths, the day-regime
throttle inputs, the structural stop placement and the calibration behind
every threshold. Those live in config as neutral reference defaults.
"""
from __future__ import annotations

import logging
import math
import statistics
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

import config
from engine.market_state import MarketState
from engine.ranking import StockRank, flows_4way
from engine.regime import RegimeMeter

log = logging.getLogger("oneway")


@dataclass(slots=True)
class OneWayMover:
    ts: datetime
    underlying: str
    direction: str            # BUY (up) | SELL (down)
    status: str               # ENTRY | OPEN | EXIT
    score: float              # 0-100
    entry_ts: datetime
    entry_price: float
    last_price: float
    pnl_pct: float            # signed with the call, + is winning
    price_pct_day: float
    build_x: float
    dominance: float
    clean_flow: float
    retrace_pct: float
    two_sided: float
    cum_net_cr: float
    monitored_min: int
    contract: str
    note: str = ""
    reasons: list[str] = field(default_factory=list)
    kind: str = "normal"
    prime_window: bool = True
    conviction: bool = False
    conv_ts: datetime | None = None
    stalling: bool = False
    stop_px: float = 0.0
    fuel_forced_cr: float = 0.0
    fuel_spec_cr: float = 0.0
    forced_share: float = 0.0
    regime: str = "MIXED"
    size: float = 1.0
    promo_pct: float = 0.0
    exit_risk: float = 0.0


class _Track:
    """Per-stock session state, updated every minute for every stock."""

    __slots__ = ("cum_net", "cum_tot", "absnet", "last_sign", "flips",
                 "decided", "anchor_px", "extreme_px", "max_pull", "dir",
                 "net_hist", "tot_hist", "two_hist", "streak", "streak_dir")

    def __init__(self):
        self.cum_net = 0.0
        self.cum_tot = 0.0
        self.absnet: list[float] = []
        self.last_sign = 0
        self.flips = 0
        self.decided = 0
        self.anchor_px = 0.0
        self.extreme_px = 0.0
        self.max_pull = 0.0
        self.dir = ""
        self.net_hist: deque[float] = deque(maxlen=config.OW_RECENT_WIN)
        self.tot_hist: deque[float] = deque(maxlen=config.OW_RECENT_WIN)
        self.two_hist: deque[float] = deque(maxlen=5)
        self.streak = 0
        self.streak_dir = ""


class _Open:
    """One live ride."""

    __slots__ = ("direction", "entry_ts", "entry_px", "score", "contract",
                 "peak_px", "peak_pnl", "last_ext_ts", "flow_since",
                 "conviction", "conv_ts", "prime", "stop_px", "size",
                 "regime", "minutes")

    def __init__(self, direction: str, ts: datetime, px: float, score: float,
                 contract: str, regime: str):
        self.direction = direction
        self.entry_ts = ts
        self.entry_px = px
        self.score = score
        self.contract = contract
        self.peak_px = px
        self.peak_pnl = 0.0
        self.last_ext_ts = ts
        self.flow_since = 0.0
        self.conviction = False
        self.conv_ts: datetime | None = None
        self.prime = ts.time() <= config.OW_BADGE_PRIME_END
        self.stop_px = 0.0
        self.size = config.REGIME_SIZE.get(regime, 1.0)
        self.regime = regime
        self.minutes = 0


class OneWayMomentum:
    def __init__(self, market: MarketState,
                 flow_baseline: dict[str, float] | None = None,
                 near_baseline: dict[str, float] | None = None):
        self.market = market
        self._track: dict[str, _Track] = {}
        self._open: dict[str, _Open] = {}
        self._done: set[str] = set()
        self._entries_today = {"BUY": 0, "SELL": 0}
        self.regime_meter = RegimeMeter()
        self.regime = "MIXED"
        self._baseline = flow_baseline or {}
        self._near_baseline = near_baseline or {}

    # ------------------------------------------------------------ public ----
    def compute(self, rows: list[StockRank], ts: datetime,
                radar: list | None = None,
                near: dict[str, tuple[float, float]] | None = None
                ) -> list[OneWayMover]:
        self.regime_meter.mark_start(ts)
        self.regime = self.regime_meter.update(self.market, ts)
        stop = config.REGIME_STOP.get(self.regime, config.OW_STOP_PCT)
        budget = config.REGIME_BUDGET.get(self.regime, config.OW_DAILY_PER_SIDE)

        out: list[OneWayMover] = []
        metrics: dict[str, dict] = {}

        for r in rows:
            m = self._update(r)
            if m is not None:
                metrics[r.underlying] = m

        for ul in list(self._open):
            mover = self._manage(ul, metrics.get(ul), ts, stop)
            if mover is not None:
                out.append(mover)

        for ul, m in metrics.items():
            if ul in self._open or ul in self._done:
                continue
            mover = self._maybe_enter(ul, m, ts, budget)
            if mover is not None:
                out.append(mover)

        out.sort(key=lambda x: (x.status != "ENTRY", -x.score))
        return out

    # ---------------------------------------------------------- metrics ----
    def _update(self, r: StockRank) -> dict | None:
        """Fold one minute of ranking data into the stock's session track."""
        tr = self._track.setdefault(r.underlying, _Track())
        bull, bear = flows_4way(r)
        net = bull - bear
        tot = bull + bear

        tr.cum_net += net
        tr.cum_tot += tot
        tr.net_hist.append(net)
        tr.tot_hist.append(tot)

        sign = 0 if abs(net) < 1e-9 else (1 if net > 0 else -1)
        if sign:
            tr.decided += 1
            if tr.last_sign and sign != tr.last_sign:
                tr.flips += 1
            tr.last_sign = sign
            tr.absnet.append(abs(net))

        two = min(bull, bear) / max(bull, bear) if max(bull, bear) > 0 else 0.0
        tr.two_hist.append(two)

        px = r.fut_price
        if px <= 0:
            return None
        if tr.anchor_px <= 0:
            tr.anchor_px = tr.extreme_px = px

        direction = "BUY" if tr.cum_net >= 0 else "SELL"
        if direction != tr.dir:
            tr.dir = direction
            tr.extreme_px = px
            tr.max_pull = 0.0

        if direction == "BUY":
            tr.extreme_px = max(tr.extreme_px, px)
            pull = (tr.extreme_px - px) / tr.extreme_px * 100
        else:
            tr.extreme_px = min(tr.extreme_px, px)
            pull = (px - tr.extreme_px) / tr.extreme_px * 100
        tr.max_pull = max(tr.max_pull, pull)

        move = abs(px - tr.anchor_px) / tr.anchor_px * 100
        retrace = tr.max_pull / move if move >= config.OW_MIN_MOVE else 0.0
        clean = 1.0 - (tr.flips / tr.decided) if tr.decided else 0.0
        two_sided = statistics.fmean(tr.two_hist) if tr.two_hist else 0.0

        recent_tot = sum(tr.tot_hist)
        dom = abs(sum(tr.net_hist)) / recent_tot if recent_tot > 0 else 0.0
        build_x = abs(tr.cum_net) / self._typical(r.underlying, tr)

        m = {
            "direction": direction, "price": px, "build_x": build_x,
            "dominance": dom, "clean": clean, "retrace": retrace,
            "two_sided": two_sided, "move": move,
            "cum_net_cr": tr.cum_net, "day_pct": r.price_pct_day,
            "from_extreme": pull, "minutes": tr.decided,
            "contract": (r.top_ce_buy_strike if direction == "BUY"
                         else r.top_pe_buy_strike),
        }
        m["score"] = self._score(m)
        return m

    def _typical(self, ul: str, tr: _Track) -> float:
        """Prior-day median flow if known, else this session's own median."""
        seeded = self._baseline.get(ul, 0.0)
        if len(tr.absnet) >= config.OW_BASELINE_MIN:
            return max(statistics.median(tr.absnet), config.OW_FLOW_FLOOR_CR)
        return max(seeded, config.OW_FLOW_FLOOR_CR)

    @staticmethod
    def _score(m: dict) -> float:
        """Magnitude x dominance x cleanliness x one-way price, 0-100."""
        if m["build_x"] <= 1.0:
            return 0.0
        magnitude = min(1.0, math.log(m["build_x"])
                        / math.log(config.OW_BUILD_FULL))
        oneway = max(0.0, 1.0 - m["retrace"])
        return 100.0 * magnitude * m["dominance"] * m["clean"] * oneway

    # ----------------------------------------------------------- entries ----
    def _maybe_enter(self, ul: str, m: dict, ts: datetime,
                     budget: int) -> OneWayMover | None:
        tr = self._track[ul]
        if not config.OW_FAST_WINDOW_START <= ts.time() <= config.OW_WINDOW_END:
            return None

        if self._gates(m):
            self._reset_streak(tr)
            return None

        if m["direction"] != tr.streak_dir:
            tr.streak_dir = m["direction"]
            tr.streak = 0
        tr.streak += 1
        if tr.streak < config.OW_MIN_STREAK:
            return None

        side = m["direction"]
        if self._entries_today[side] >= budget:
            return None
        if sum(1 for o in self._open.values() if o.direction == side) \
                >= config.OW_MAX_PER_SIDE:
            return None

        o = _Open(side, ts, m["price"], m["score"], m["contract"], self.regime)
        stop = config.REGIME_STOP.get(self.regime, config.OW_STOP_PCT)
        o.stop_px = (m["price"] * (1 - stop / 100) if side == "BUY"
                     else m["price"] * (1 + stop / 100))
        self._open[ul] = o
        self._entries_today[side] += 1
        log.info("ONE-WAY ENTRY %s %s @ %.2f score=%.0f build=%.1fx",
                 ul, side, m["price"], m["score"], m["build_x"])
        return self._mk(ul, "ENTRY", ts, o, m, reasons=self._reasons(m))

    @staticmethod
    def _gates(m: dict) -> list[str]:
        """Hard rejections. A non-empty list means the stock cannot enter."""
        bad = []
        if m["minutes"] < config.OW_MIN_STREAK:
            bad.append("warmup")
        if m["build_x"] < config.OW_MIN_BUILD_X:
            bad.append("build")
        if m["dominance"] < config.OW_MIN_RECENT_DOM:
            bad.append("dominance")
        if m["clean"] < config.OW_MIN_CLEAN:
            bad.append("choppy flow")
        if m["two_sided"] > config.OW_MAX_TWO_SIDED:
            bad.append("two-sided")
        if m["retrace"] > config.OW_RETRACE_MAX:
            bad.append("retraced")
        if m["from_extreme"] > config.OW_MAX_FROM_EXTREME:
            bad.append("off extreme")
        if m["score"] < config.OW_MIN_SCORE:
            bad.append("score")
        return bad

    @staticmethod
    def _reasons(m: dict) -> list[str]:
        return [f"build {m['build_x']:.0f}x typical",
                f"dominance {m['dominance']:.2f}",
                f"clean {m['clean']:.2f}",
                f"retrace {m['retrace']:.2f}"]

    @staticmethod
    def _reset_streak(tr: _Track) -> None:
        tr.streak = 0
        tr.streak_dir = ""

    # ------------------------------------------------------- open rides ----
    def _manage(self, ul: str, m: dict | None, ts: datetime,
                stop: float) -> OneWayMover | None:
        o = self._open[ul]
        o.minutes += 1
        px = m["price"] if m else o.peak_px
        pnl = self._pnl(o, px)

        if o.direction == "BUY":
            fresh = px > o.peak_px
            o.peak_px = max(o.peak_px, px)
        else:
            fresh = px < o.peak_px
            o.peak_px = min(o.peak_px, px)
        if fresh:
            o.last_ext_ts = ts
        o.peak_pnl = max(o.peak_pnl, pnl)
        if m:
            o.flow_since = (m["cum_net_cr"] if o.direction == "BUY"
                            else -m["cum_net_cr"])

        self._promote(o, pnl, ts)

        reason = self._exit_reason(o, pnl, ts, stop)
        if reason:
            del self._open[ul]
            self._done.add(ul)
            log.info("ONE-WAY EXIT %s %s @ %.2f pnl=%+.2f%% (%s)",
                     ul, o.direction, px, pnl, reason)
            return self._mk(ul, "EXIT", ts, o, m, note=reason)

        return self._mk(ul, "OPEN", ts, o, m)

    @staticmethod
    def _pnl(o: _Open, px: float) -> float:
        if o.entry_px <= 0:
            return 0.0
        raw = (px - o.entry_px) / o.entry_px * 100
        return raw if o.direction == "BUY" else -raw

    @staticmethod
    def _exit_reason(o: _Open, pnl: float, ts: datetime, stop: float) -> str:
        if pnl <= -stop:
            return f"stop {stop:.2f}%"
        if (o.peak_pnl >= config.OW_RIDE_MIN_PEAK
                and pnl <= o.peak_pnl * config.OW_RIDE_TRAIL):
            return f"gave back from {o.peak_pnl:+.2f}%"
        if ts.time() >= config.OW_EOD_EXIT:
            return "end of day"
        return ""

    # ------------------------------------------------- conviction funnel ----
    @staticmethod
    def _promote(o: _Open, pnl: float, ts: datetime) -> None:
        """Four legs, all required, sticky once earned."""
        if o.conviction:
            return
        if (ts - o.entry_ts).total_seconds() / 60 < config.CONV_MIN_SURVIVED_MIN:
            return
        if (ts - o.last_ext_ts).total_seconds() / 60 > config.CONV_FRESH_EXT_WIN:
            return
        if o.flow_since <= config.CONV_FLOW_MIN_CR:
            return
        if pnl < config.CONV_MIN_PNL:
            return
        if not o.prime and not config.CONV_ALLOW_NORMAL:
            return
        o.conviction = True
        o.conv_ts = ts

    @staticmethod
    def _promo_pct(o: _Open, pnl: float, ts: datetime) -> float:
        """Display meter: how close an open probe is to promotion."""
        held = (ts - o.entry_ts).total_seconds() / 60
        legs = [min(1.0, held / config.CONV_MIN_SURVIVED_MIN),
                1.0 if (ts - o.last_ext_ts).total_seconds() / 60
                <= config.CONV_FRESH_EXT_WIN else 0.0,
                1.0 if o.flow_since > config.CONV_FLOW_MIN_CR else 0.0,
                min(1.0, max(0.0, pnl) / max(config.CONV_MIN_PNL, 1e-9))]
        return 100.0 * sum(legs) / len(legs)

    @staticmethod
    def _exit_risk(o: _Open, pnl: float, stop: float) -> float:
        """Display meter: how close a ride is to being removed."""
        to_stop = 1.0 - min(1.0, max(0.0, pnl + stop) / max(stop, 1e-9))
        give = 0.0
        if o.peak_pnl >= config.OW_RIDE_MIN_PEAK:
            give = min(1.0, max(0.0, o.peak_pnl - pnl)
                       / max(o.peak_pnl * (1 - config.OW_RIDE_TRAIL), 1e-9))
        return 100.0 * max(to_stop, give)

    # ------------------------------------------------------------ output ----
    def _mk(self, ul: str, status: str, ts: datetime, o: _Open,
            m: dict | None, note: str = "",
            reasons: list[str] | None = None) -> OneWayMover:
        px = m["price"] if m else o.peak_px
        pnl = self._pnl(o, px)
        stop = config.REGIME_STOP.get(o.regime, config.OW_STOP_PCT)
        stale = (ts - o.last_ext_ts).total_seconds() / 60
        return OneWayMover(
            ts=ts, underlying=ul, direction=o.direction, status=status,
            score=(m["score"] if m else o.score),
            entry_ts=o.entry_ts, entry_price=o.entry_px, last_price=px,
            pnl_pct=pnl,
            price_pct_day=(m["day_pct"] if m else 0.0),
            build_x=(m["build_x"] if m else 0.0),
            dominance=(m["dominance"] if m else 0.0),
            clean_flow=(m["clean"] if m else 0.0),
            retrace_pct=(m["retrace"] if m else 0.0),
            two_sided=(m["two_sided"] if m else 0.0),
            cum_net_cr=(m["cum_net_cr"] if m else 0.0),
            monitored_min=o.minutes, contract=o.contract, note=note,
            reasons=reasons or [], kind="normal",
            prime_window=o.prime, conviction=o.conviction, conv_ts=o.conv_ts,
            stalling=bool(o.conviction and stale > config.CONV_STALL_MIN),
            stop_px=o.stop_px, regime=o.regime, size=o.size,
            promo_pct=self._promo_pct(o, pnl, ts),
            exit_risk=self._exit_risk(o, pnl, stop),
        )
