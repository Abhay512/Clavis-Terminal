"""OI build-up multiple board: today's OI versus the prior EOD snapshot.

Reference implementation. The production board's baseline selection, near-spot
weighting, writer read and counter-tape flag are not published; this version
tracks the plain running multiple of each near-spot contract against its own
session base.
"""
from __future__ import annotations

import csv
import logging
import statistics
from dataclasses import dataclass
from datetime import date, datetime

import config
from engine import classifier, oi_engine
from engine.market_state import InstrumentState, MarketState

log = logging.getLogger("oimult")


def load_prev_eod_oi(today: date | None = None) -> dict[tuple, tuple]:
    """Most recent prior-session EOD OI snapshot, keyed by contract."""
    today = today or date.today()
    best = None
    for p in sorted(config.META_DIR.glob("*_eod_oi.csv")):
        try:
            d = date.fromisoformat(p.name[:10])
        except ValueError:
            continue
        if d < today:
            best = p
    if best is None:
        return {}
    out: dict[tuple, tuple] = {}
    try:
        with open(best, newline="") as f:
            for row in csv.DictReader(f):
                if row.get("kind") in ("CE", "PE"):
                    out[(row["underlying"], row["kind"],
                         float(row["strike"]), row["expiry"])] = (
                        int(float(row["oi_close"])),
                        float(row["last_price"]))
    except Exception:
        log.exception("failed reading EOD OI snapshot %s", best)
        return {}
    log.info("OI-multiple fallback baselines: %d options from %s",
             len(out), best.name)
    return out


@dataclass(slots=True)
class OIMultipleRow:
    ts: datetime
    underlying: str
    running_max: float        # highest OI multiple seen today
    contract: str             # the contract holding that multiple
    base_oi: int
    peak_oi: int
    t_max: datetime           # minute the running max was set
    first_2x: datetime | None  # first minute any contract passed the checkpoint
    strikes_2x: int           # contracts past the checkpoint
    direction: str            # BUY | SELL | MIXED
    dominance: float
    bull_cr: float
    bear_cr: float
    top_writer: bool          # the top contract's premium fell as OI grew
    fresh: str                # biggest build off a near-zero base
    fut_price: float
    price_pct_day: float
    monitored_min: int
    counter_tape: bool = False


class _Tok:
    """Per-option running state: session base plus near-spot peaks."""

    __slots__ = ("base", "base_px", "strike", "kind", "max_mult", "peak_oi",
                 "peak_px", "eligible")

    def __init__(self, state: InstrumentState,
                 prev: tuple[int, float] | None = None):
        bars = state.bars
        first = bars[0] if bars else None
        self.strike = state.inst.strike
        self.kind = state.inst.kind
        self.eligible = bool(
            first is not None
            and first.minute.time() <= config.OIM_BASE_CUTOFF)
        self.base = int(first.oi) if first is not None else 0
        self.base_px = float(first.close) if first is not None else 0.0
        if not self.eligible and prev is not None:
            self.base, self.base_px = prev
            self.eligible = True
        self.max_mult = 0.0
        self.peak_oi = 0
        self.peak_px = 0.0


class _Stock:
    __slots__ = ("running_max", "top_contract", "top_tok", "t_max",
                 "first_2x", "toks", "hit2")

    def __init__(self):
        self.running_max = 0.0
        self.top_contract = ""
        self.top_tok: _Tok | None = None
        self.t_max: datetime | None = None
        self.first_2x: datetime | None = None
        self.toks: dict[int, _Tok] = {}
        self.hit2: set[int] = set()


class OIMultipleBoard:
    def __init__(self, market: MarketState,
                 prev_eod: dict[tuple, tuple] | None = None):
        self.market = market
        self._prev_eod = (prev_eod if prev_eod is not None
                          else load_prev_eod_oi())
        self._chains: dict[str, dict[float, dict[str, InstrumentState]]] = {}
        self._step: dict[str, float] = {}
        for ul, states in market.options_by_underlying.items():
            chain: dict[float, dict[str, InstrumentState]] = {}
            for s in states:
                chain.setdefault(s.inst.strike, {})[s.inst.kind] = s
            self._chains[ul] = chain
            strikes = sorted(chain)
            diffs = [b - a for a, b in zip(strikes, strikes[1:]) if b > a]
            self._step[ul] = statistics.median(diffs) if diffs else 0.0
        self._stocks: dict[str, _Stock] = {}

    def compute(self, ts: datetime) -> list[OIMultipleRow]:
        """The displayed board, capped per direction."""
        counts = {"BUY": 0, "SELL": 0, "MIXED": 0}
        caps = {"BUY": config.OIM_TOP_N, "SELL": config.OIM_TOP_N,
                "MIXED": config.OIM_MIXED_N}
        out: list[OIMultipleRow] = []
        for r in self.full_board(ts):
            if counts[r.direction] < caps[r.direction]:
                counts[r.direction] += 1
                out.append(r)
        return out

    def full_board(self, ts: datetime) -> list[OIMultipleRow]:
        """Every stock past the checkpoint, sorted by running max."""
        rows = []
        for ul, chain in self._chains.items():
            row = self._scan(ul, chain, ts)
            if row is not None:
                rows.append(row)
        rows.sort(key=lambda r: r.running_max, reverse=True)
        return rows

    # ------------------------------------------------------------ per stock
    def _scan(self, ul, chain, ts) -> OIMultipleRow | None:
        fut = self.market.futures_by_underlying.get(ul)
        step = self._step.get(ul, 0.0)
        if fut is None or fut.last_price <= 0 or step <= 0:
            return None
        spot = fut.last_price
        span = config.OIM_NEAR_STEPS * step
        stk = self._stocks.setdefault(ul, _Stock())
        to_cr = spot / 1e7

        bull = bear = 0.0
        fresh = (0, "")

        for strike, kinds in chain.items():
            if abs(strike - spot) > span:
                continue
            for kind, state in kinds.items():
                if not state.bars:
                    continue
                tok = stk.toks.get(state.inst.token)
                if tok is None:
                    prev = self._prev_eod.get(
                        (ul, kind, strike, state.inst.expiry.isoformat()))
                    tok = _Tok(state, prev)
                    stk.toks[state.inst.token] = tok
                if not tok.eligible or tok.base < config.OIM_MIN_BASE:
                    continue

                oi_now = int(state.bars[-1].oi)
                mult = oi_now / tok.base
                if oi_now > tok.peak_oi:
                    tok.peak_oi = oi_now
                    tok.peak_px = float(state.bars[-1].close)
                if mult > tok.max_mult:
                    tok.max_mult = mult

                added = oi_now - tok.base
                if added >= config.OIM_FRESH_MIN and added > fresh[0]:
                    fresh = (added, f"{strike:g}{kind} +{added // 1000}k")

                if mult >= config.OIM_CHECKPOINT:
                    stk.hit2.add(state.inst.token)
                    if stk.first_2x is None:
                        stk.first_2x = ts
                if mult > stk.running_max:
                    stk.running_max = mult
                    stk.top_contract = f"{strike:g}{kind}"
                    stk.top_tok = tok
                    stk.t_max = ts

                m = oi_engine.compute(state, config.RADAR_WINDOW,
                                      intrabar=False)
                if m is None or m.oi_delta <= 0:
                    continue
                side = classifier.option_side(
                    classifier.classify(m.oi_delta, m.price_pct))
                if side is None:
                    continue
                cr = m.oi_delta * to_cr
                if ((kind == "CE" and side == classifier.BUY_SIDE)
                        or (kind == "PE" and side == classifier.SELL_SIDE)):
                    bull += cr
                else:
                    bear += cr

        if stk.running_max < config.OIM_CHECKPOINT or stk.top_tok is None:
            return None

        total = bull + bear
        dom = abs(bull - bear) / total if total > 0 else 0.0
        if dom < config.OIM_MIN_DOM:
            direction = "MIXED"
        else:
            direction = "BUY" if bull > bear else "SELL"

        tok = stk.top_tok
        return OIMultipleRow(
            ts=ts, underlying=ul, running_max=round(stk.running_max, 1),
            contract=stk.top_contract, base_oi=tok.base, peak_oi=tok.peak_oi,
            t_max=stk.t_max or ts, first_2x=stk.first_2x,
            strikes_2x=len(stk.hit2), direction=direction,
            dominance=round(dom, 2), bull_cr=round(bull, 1),
            bear_cr=round(bear, 1),
            top_writer=bool(tok.base_px > 0 and tok.peak_px < tok.base_px),
            fresh=fresh[1], fut_price=spot,
            price_pct_day=round(fut.day_pct(), 2),
            monitored_min=fut.bars_seen,
        )
