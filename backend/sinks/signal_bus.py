"""Pub/sub hub decoupling the engine from console, storage and API sinks."""
from __future__ import annotations

import logging
from collections.abc import Callable

import config
from engine.big_player_radar import BigPlayerSignal
from engine.oi_multiple import OIMultipleRow
from engine.oneway_momentum import OneWayMover
from engine.position_radar import PositionBuild
from engine.ranking import StockRank
from engine.sector_leaders import SectorLeader
from engine.spike_detector import Signal

log = logging.getLogger("bus")


class SignalBus:
    def __init__(self):
        self._signal_subs: list[Callable[[Signal], None]] = []
        self._ranking_subs: list[Callable[[list[StockRank]], None]] = []
        self._position_subs: list[Callable[[list[PositionBuild]], None]] = []
        self._oneway_subs: list[Callable[[list[OneWayMover]], None]] = []
        self._radar_subs: list[Callable[[list[BigPlayerSignal]], None]] = []
        self._oimult_subs: list[Callable[[list[OIMultipleRow]], None]] = []
        self._sector_subs: list[Callable[[list[SectorLeader]], None]] = []
        self._feed_subs: list[Callable[[dict], None]] = []

    def on_signal(self, fn: Callable[[Signal], None]) -> None:
        self._signal_subs.append(fn)

    def on_ranking(self, fn: Callable[[list[StockRank]], None]) -> None:
        self._ranking_subs.append(fn)

    def publish_signal(self, sig: Signal) -> None:
        for fn in self._signal_subs:
            try:
                fn(sig)
            except Exception:
                log.exception("signal subscriber failed")

    def publish_ranking(self, rows: list[StockRank]) -> None:
        for fn in self._ranking_subs:
            try:
                fn(rows)
            except Exception:
                log.exception("ranking subscriber failed")

    def on_position(self, fn: Callable[[list[PositionBuild]], None]) -> None:
        self._position_subs.append(fn)

    def publish_position(self, builds: list[PositionBuild]) -> None:
        for fn in self._position_subs:
            try:
                fn(builds)
            except Exception:
                log.exception("position subscriber failed")

    def on_oneway(self, fn: Callable[[list[OneWayMover]], None]) -> None:
        self._oneway_subs.append(fn)

    def publish_oneway(self, movers: list[OneWayMover]) -> None:
        for fn in self._oneway_subs:
            try:
                fn(movers)
            except Exception:
                log.exception("oneway subscriber failed")

    def on_radar(self, fn: Callable[[list[BigPlayerSignal]], None]) -> None:
        self._radar_subs.append(fn)

    def publish_radar(self, sigs: list[BigPlayerSignal]) -> None:
        for fn in self._radar_subs:
            try:
                fn(sigs)
            except Exception:
                log.exception("radar subscriber failed")

    def on_oimult(self, fn: Callable[[list[OIMultipleRow]], None]) -> None:
        self._oimult_subs.append(fn)

    def publish_oimult(self, rows: list[OIMultipleRow]) -> None:
        for fn in self._oimult_subs:
            try:
                fn(rows)
            except Exception:
                log.exception("oimult subscriber failed")

    def on_sector(self, fn: Callable[[list[SectorLeader]], None]) -> None:
        self._sector_subs.append(fn)

    def publish_sector(self, rows: list[SectorLeader]) -> None:
        for fn in self._sector_subs:
            try:
                fn(rows)
            except Exception:
                log.exception("sector subscriber failed")

    def on_feed(self, fn: Callable[[dict], None]) -> None:
        self._feed_subs.append(fn)

    def publish_feed(self, status: dict) -> None:
        """Feed-health updates from the watchdog (feed_down flag + note);
        the API merges them into /api/status -> dashboard red banner."""
        for fn in self._feed_subs:
            try:
                fn(status)
            except Exception:
                log.exception("feed-status subscriber failed")


# ------------------------------------------------------------ console ------
def print_signal(sig: Signal) -> None:
    tag = "TICK" if sig.intrabar else "BAR "
    strike = f"{sig.strike:g}{sig.kind}" if sig.kind != "FUT" else "FUT"
    side = f" [{sig.side}]" if sig.side else ""
    print(f"{sig.ts:%H:%M:%S} {tag} SPIKE {sig.underlying:<12}{strike:<10} "
          f"{sig.classification:<15}{side:<12} "
          f"dOI {sig.oi_delta:+,} ({sig.oi_pct:+.1f}%) z={sig.zscore:.1f} "
          f"~Rs {sig.notional_cr:.1f}cr score={sig.score:.0f}")


# (still stored in SQLite for analysis).
RANK_DISPLAY_MIN_CR = 0.1
_COL_W = 43  # width of one ranking column block


def print_rankings(rows: list[StockRank], top_n: int = 10) -> None:
    from engine.ranking import StockRanker
    buys = [r for r in StockRanker.top_buy(rows, top_n)
            if r.buy_notional_cr >= RANK_DISPLAY_MIN_CR]
    sells = [r for r in StockRanker.top_sell(rows, top_n)
             if r.sell_notional_cr >= RANK_DISPLAY_MIN_CR]
    if not buys and not sells:
        return
    ts = rows[0].ts if rows else ""
    print(f"\n===== OI BUILD-UP RANKING {ts:%H:%M} (5-min window) =====")
    print(f"{'-- TOP BUY-SIDE (option buying) --':<{_COL_W}} | "
          f"{'-- TOP SELL-SIDE (option writing) --'}")
    header = f"{'#':<3}{'Stock':<12}{'Rs cr':>8}  {'Top strike':<18}"
    print(f"{header} | {header}")
    for i in range(max(len(buys), len(sells))):
        left = right = " " * _COL_W
        if i < len(buys):
            b = buys[i]
            left = (f"{i + 1:<3}{b.underlying:<12}{b.buy_notional_cr:>8.1f}  "
                    f"{b.top_buy_strike:<18}")
        if i < len(sells):
            s = sells[i]
            right = (f"{i + 1:<3}{s.underlying:<12}{s.sell_notional_cr:>8.1f}  "
                     f"{s.top_sell_strike:<18}")
        print(f"{left} | {right}")
    print()


def print_radar(sigs: list[BigPlayerSignal]) -> None:
    if not sigs:
        return
    ts = sigs[0].ts
    print(f"\n##### BIG PLAYER RADAR {ts:%H:%M} "
          f"(near-spot +/-{config.RADAR_ATM_STRIKES} strike OI) #####")
    print(f"{'Dir':<5}{'Stock':<12}{'Str':>5}{'nearDom':>8}{'Net':>7}"
          f"{'LTP':>10}{'Day%':>7}  {'top CE':<16}{'top PE':<16}")
    for s in sigs:
        print(f"{s.direction:<5}{s.underlying:<12}{s.strength:>5.0f}"
              f"{s.near_dom:>8.2f}{s.net_cr:>+6.0f}c{s.fut_price:>10.1f}"
              f"{s.price_pct_day:>+7.1f}  {s.ce_strike:<16}{s.pe_strike:<16}")
    print()


def print_oneway(movers: list[OneWayMover]) -> None:
    if not movers:
        return
    ts = movers[0].ts
    [m for m in movers if m.direction == "BUY"]
    [m for m in movers if m.direction == "SELL"]
    print(f"\n>>>>> ONE-WAY MOVERS {ts:%H:%M} "
          f"(clean institutional one-directional) <<<<<")
    print(f"{'St':<7}{'Side':<5}{'Stock':<12}{'Score':>6}{'Entry':>16}"
          f"{'Now':>9}{'P&L%':>7}{'Build':>7}{'Eff':>5}  Contract / note")
    for m in movers:
        entry = f"{m.entry_ts:%H:%M} @ {m.entry_price:.1f}"
        side = "UP" if m.direction == "BUY" else "DOWN"
        tail = m.note if m.status == "EXIT" else m.contract
        if m.conviction and m.status != "EXIT":
            conv_t = f"{m.conv_ts:%H:%M}" if m.conv_ts else "?"
            tail = (f"*CONVICTION {conv_t}"
                    f"{' STALLING' if m.stalling else ''}*  {tail}")
        print(f"{m.status:<7}{side:<5}{m.underlying:<12}{m.score:>6.0f}"
              f"{entry:>16}{m.last_price:>9.1f}{m.pnl_pct:>+7.2f}"
              f"{m.build_x:>6.0f}x{m.clean_flow:>5.2f}  {tail}")
    print()


def print_oimult(rows: list[OIMultipleRow]) -> None:
    if not rows:
        return
    ts = rows[0].ts
    print(f"\n***** OI BUILD-UP MULTIPLE BOARD {ts:%H:%M} "
          f"(near-spot +/-{config.OIM_NEAR_STEPS}, ranked by max multiple) *****")
    print(f"{'Dir':<6}{'Stock':<12}{'Max':>7}{'Contract':<11}{'W?':<3}"
          f"{'first2x':>8}{'tMax':>6}{'n2x':>4}{'Dom':>5}{'Day%':>7}  Fresh")
    for r in rows:
        f2 = f"{r.first_2x:%H:%M}" if r.first_2x else "-"
        print(f"{r.direction:<6}{r.underlying:<12}{r.running_max:>6.1f}x"
              f"{r.contract:<11}{'W' if r.top_writer else 'B':<3}"
              f"{f2:>8}{r.t_max:%H:%M}{r.strikes_2x:>4}{r.dominance:>5.2f}"
              f"{r.price_pct_day:>+7.2f}  {r.fresh}")
    print()


def print_position(builds: list[PositionBuild]) -> None:
    if not builds:
        return
    ts = builds[0].ts
    print(f"\n%%%%% POSITION RADAR {ts:%H:%M} "
          f"(where big money is building TODAY) %%%%%")
    print(f"{'Dir':<5}{'Stock':<12}{'Phase':<10}{'Score':>6}{'CumFlow':>9}"
          f"{'Dom':>5}{'Pers':>6}{'Day%':>7}{'Brk':>7}  "
          f"{'CE wall':<18}{'PE wall':<18}Note")
    for b in builds:
        brk = f"{b.breakout_ts:%H:%M}" if b.breakout_ts else "-"
        print(f"{b.direction:<5}{b.underlying:<12}{b.phase:<10}"
              f"{b.score:>6.0f}{b.cum_net_cr:>8.0f}c{b.dominance:>5.2f}"
              f"{b.persistence:>6.2f}{b.price_pct_day:>+7.2f}{brk:>7}  "
              f"{b.ce_wall:<18}{b.pe_wall:<18}{b.note}")
    print()


