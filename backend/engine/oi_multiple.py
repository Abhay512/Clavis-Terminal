"""OI build-up multiple board: today's OI versus the prior EOD snapshot."""
from __future__ import annotations

import csv
import logging
import statistics
from dataclasses import dataclass
from datetime import date, datetime

import config
from engine.market_state import InstrumentState, MarketState

log = logging.getLogger("oimult")


def load_prev_eod_oi(today: date | None = None) -> dict[tuple, tuple]:
    """Most recent prior-session EOD OI snapshot, keyed by (underlying, kind, strike)."""
    today = today or date.today()
    snaps = sorted(config.META_DIR.glob("*_eod_oi.csv"))
    best = None
    for p in snaps:
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
    running_max: float        # highest near-spot multiple reached today
    contract: str             # the strike that set it, e.g. "530PE"
    base_oi: int              # that strike's open baseline
    peak_oi: int              # that strike's peak OI while near spot
    t_max: datetime           # when the max printed
    first_2x: datetime | None # first minute any near-spot strike hit 2x
    strikes_2x: int           # near-spot strikes that reached >= 2x today
    direction: str            # BUY | SELL | MIXED (premium overlay)
    dominance: float          # max(bull,bear)/(bull+bear), 0.5=mixed 1=clean
    bull_cr: float            # Rs-cr-weighted bullish build
    bear_cr: float
    top_writer: bool          # top contract's premium FELL base->peak
    #                           (writers, not buyers - changes the reading)
    fresh: str                # biggest near-zero-base build, "540CE +4050k"
    fut_price: float
    price_pct_day: float
    monitored_min: int
    counter_tape: bool = False  # direction fades a broadly one-way tape.


class _Tok:
    """Per-option running state (baseline + near-spot peaks)."""
    __slots__ = ("base", "base_px", "strike", "kind", "max_mult",
                 "peak_oi", "peak_px", "eligible")

    def __init__(self, state: InstrumentState,
                 prev: tuple[int, float] | None = None):
        bars = state.bars
        self.strike = state.inst.strike
        self.kind = state.inst.kind
        first = bars[0] if bars else None
        self.eligible = bool(
            first is not None
            and first.minute.time() <= config.OIM_BASE_CUTOFF)
        self.base = int(first.oi) if first is not None else 0
        self.base_px = float(first.close) if first is not None else 0.0
        if not self.eligible and prev is not None:
            self.base, self.base_px = prev
            self.eligible = True
        self.max_mult = 0.0
        self.peak_oi = 0        # max OI seen while near spot
        self.peak_px = 0.0      # option premium at that peak minute


class _Stock:
    __slots__ = ("running_max", "top_contract", "top_tok", "t_max",
                 "first_2x", "toks", "qualified", "hit2")

    def __init__(self):
        self.running_max = 0.0
        self.top_contract = ""
        self.top_tok: _Tok | None = None
        self.t_max: datetime | None = None
        self.first_2x: datetime | None = None
        self.toks: dict[int, _Tok] = {}
        self.qualified: set[int] = set()   # tokens feeding the direction read
        self.hit2: set[int] = set()        # tokens that reached >= 2x


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
        rows = self.full_board(ts)
        out: list[OIMultipleRow] = []
        counts = {"BUY": 0, "SELL": 0, "MIXED": 0}
        caps = {"BUY": config.OIM_TOP_N, "SELL": config.OIM_TOP_N,
                "MIXED": config.OIM_MIXED_N}
        for r in rows:
            if counts[r.direction] < caps[r.direction]:
                counts[r.direction] += 1
                out.append(r)
        return out

    def full_board(self, ts: datetime) -> list[OIMultipleRow]:
        """Every stock past the 2x checkpoint, untruncated, sorted by
        running max - the eval/research view of the board."""
        rows: list[OIMultipleRow] = []
        for ul, chain in self._chains.items():
            row = self._scan(ul, chain, ts)
            if row is not None:
                rows.append(row)
        rows.sort(key=lambda r: r.running_max, reverse=True)

        up = dn = 0
        for fut in self.market.futures_by_underlying.values():
            if fut.last_price <= 0:
                continue
            d = fut.day_pct()
            if d > 0.25:
                up += 1
            elif d < -0.25:
                dn += 1
        lopsided = (max(up, dn) >= config.OIM_TAPE_MIN
                    and max(up, dn) >= config.OIM_TAPE_RATIO
                    * max(1, min(up, dn)))
        if lopsided:
            majority = "BUY" if up >= dn else "SELL"
            for r in rows:
                if r.direction in ("BUY", "SELL") and r.direction != majority:
                    r.counter_tape = True
        return rows

    # ------------------------------------------------------------ per stock
    def _scan(self, ul, chain, ts) -> OIMultipleRow | None:
        fut = self.market.futures_by_underlying.get(ul)
        step = self._step.get(ul, 0.0)
        if fut is None or fut.last_price <= 0 or step <= 0:
            return None
        spot = fut.last_price
        stk = self._stocks.setdefault(ul, _Stock())
        span = config.OIM_NEAR_STEPS * step

        for strike, kinds in chain.items():
            if abs(strike - spot) > span:
                continue
            for kind, state in kinds.items():
                if state.last_oi <= 0 or not state.bars:
                    continue
                token = state.inst.token
                tok = stk.toks.get(token)
                if tok is None:
                    prev = self._prev_eod.get(
                        (ul, kind, float(strike), str(state.inst.expiry)))
                    tok = stk.toks[token] = _Tok(state, prev)
                if not tok.eligible:
                    continue
                oi_now = state.last_oi
                px_now = state.last_price
                if oi_now > tok.peak_oi:
                    tok.peak_oi = oi_now
                    tok.peak_px = px_now
                if tok.base >= config.OIM_MIN_BASE:
                    mult = oi_now / tok.base
                    if mult > tok.max_mult:
                        tok.max_mult = mult
                    if mult >= config.OIM_CHECKPOINT:
                        stk.hit2.add(token)
                        if stk.first_2x is None:
                            stk.first_2x = ts
                        stk.qualified.add(token)
                    if mult > stk.running_max:
                        stk.running_max = mult
                        stk.top_contract = f"{strike:g}{kind}"
                        stk.top_tok = tok
                        stk.t_max = ts
                elif tok.peak_oi >= config.OIM_FRESH_MIN:
                    stk.qualified.add(token)     # fresh-strike build

        if stk.running_max < config.OIM_CHECKPOINT:
            return None

        bull = bear = 0.0
        best_fresh = (0, "")                     # (added, label)
        for token in stk.qualified:
            tok = stk.toks[token]
            added = tok.peak_oi - tok.base
            if added <= 0 or tok.base_px <= 0 or tok.peak_px <= 0:
                continue
            buying = tok.peak_px > tok.base_px
            w = added * tok.peak_px / 1e7
            if (tok.kind == "CE") == buying:     # CE-buy / PE-write
                bull += w
            else:                                # PE-buy / CE-write
                bear += w
            if tok.base < config.OIM_MIN_BASE and added > best_fresh[0]:
                best_fresh = (added,
                              f"{tok.strike:g}{tok.kind} +{added // 1000}k")
        tot = bull + bear
        if tot > 0:
            dom = max(bull, bear) / tot
            direction = ("BUY" if bull >= bear else "SELL") \
                if dom >= config.OIM_MIN_DOM else "MIXED"
        else:
            dom, direction = 0.0, "MIXED"

        top = stk.top_tok
        top_writer = bool(top and top.peak_px < top.base_px)
        return OIMultipleRow(
            ts=ts, underlying=ul,
            running_max=round(stk.running_max, 1),
            contract=stk.top_contract,
            base_oi=top.base if top else 0,
            peak_oi=top.peak_oi if top else 0,
            t_max=stk.t_max or ts, first_2x=stk.first_2x,
            strikes_2x=len(stk.hit2),
            direction=direction, dominance=round(dom, 2),
            bull_cr=round(bull, 1), bear_cr=round(bear, 1),
            top_writer=top_writer,
            fresh=best_fresh[1],
            fut_price=spot, price_pct_day=round(fut.day_pct(), 2),
            monitored_min=fut.bars_seen,
        )
