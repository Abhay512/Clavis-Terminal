"""Build the monitored instrument universe from the NFO instrument dump."""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import config

log = logging.getLogger("universe")


@dataclass(frozen=True)
class Instrument:
    token: int
    tradingsymbol: str
    underlying: str          # e.g. RELIANCE
    kind: str                # FUT | CE | PE
    strike: float            # 0.0 for futures
    lot_size: int
    expiry: date


@dataclass
class Universe:
    instruments: list[Instrument] = field(default_factory=list)
    by_token: dict[int, Instrument] = field(default_factory=dict)
    missing_symbols: list[str] = field(default_factory=list)

    def tokens(self) -> list[int]:
        return [i.token for i in self.instruments]

    def finalize(self) -> None:
        self.by_token = {i.token: i for i in self.instruments}


def _parse_expiry(raw) -> date:
    if isinstance(raw, date):
        return raw
    return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()


def _futures_ltp(kite, futures: list[Instrument]) -> dict[str, float]:
    """Bootstrap ATM anchors: futures last price per underlying via REST."""
    ltp: dict[str, float] = {}
    keys = [f"NFO:{f.tradingsymbol}" for f in futures]
    for i in range(0, len(keys), config.QUOTE_BATCH):
        batch = keys[i:i + config.QUOTE_BATCH]
        try:
            data = kite.ltp(batch)
        except Exception as exc:
            log.warning("LTP bootstrap batch failed: %s", exc)
            continue
        for key, row in data.items():
            sym = key.split(":", 1)[1]
            for f in futures:
                if f.tradingsymbol == sym:
                    ltp[f.underlying] = float(row["last_price"])
                    break
    return ltp


def build_universe(kite, symbols: list[str], today: date | None = None) -> Universe:
    today = today or date.today()
    log.info("Downloading NFO instruments dump...")
    dump = kite.instruments("NFO")
    log.info("NFO dump: %d rows", len(dump))

    wanted = set(symbols)
    futures_by_name: dict[str, list[dict]] = {}
    options_by_name: dict[str, list[dict]] = {}
    for row in dump:
        name = row.get("name", "")
        if name not in wanted:
            continue
        expiry = _parse_expiry(row["expiry"])
        if expiry < today:
            continue
        row["_expiry"] = expiry
        itype = row.get("instrument_type", "")
        if itype == "FUT":
            futures_by_name.setdefault(name, []).append(row)
        elif itype in ("CE", "PE"):
            options_by_name.setdefault(name, []).append(row)

    uni = Universe()
    futures: list[Instrument] = []
    chain_rows: dict[str, list[Instrument]] = {}

    for sym in symbols:
        futs = futures_by_name.get(sym, [])
        opts = options_by_name.get(sym, [])
        if not futs and not opts:
            uni.missing_symbols.append(sym)
            log.warning("Symbol %s not found in NFO dump - check spelling "
                        "against the Kite `name` field.", sym)
            continue

        if futs:
            near_fut = min(futs, key=lambda r: r["_expiry"])
            futures.append(Instrument(
                token=int(near_fut["instrument_token"]),
                tradingsymbol=near_fut["tradingsymbol"],
                underlying=sym, kind="FUT", strike=0.0,
                lot_size=int(near_fut["lot_size"]),
                expiry=near_fut["_expiry"],
            ))

        if opts:
            nearest_exp = min(r["_expiry"] for r in opts)
            chain = [Instrument(
                token=int(r["instrument_token"]),
                tradingsymbol=r["tradingsymbol"],
                underlying=sym, kind=r["instrument_type"],
                strike=float(r["strike"]),
                lot_size=int(r["lot_size"]),
                expiry=r["_expiry"],
            ) for r in opts if r["_expiry"] == nearest_exp]
            chain_rows[sym] = chain

    total = len(futures) + sum(len(c) for c in chain_rows.values())
    log.info("Raw universe: %d futures + %d option contracts = %d",
             len(futures), total - len(futures), total)

    if total > config.UNIVERSE_CAPACITY:
        chain_rows = _trim_to_capacity(kite, futures, chain_rows, total)

    uni.instruments = list(futures)
    for chain in chain_rows.values():
        uni.instruments.extend(chain)
    uni.finalize()
    log.info("Final universe: %d instruments across %d stocks "
             "(%d symbols missing)", len(uni.instruments),
             len(chain_rows), len(uni.missing_symbols))
    return uni


def _trim_to_capacity(kite, futures: list[Instrument],
                      chain_rows: dict[str, list[Instrument]],
                      total: int) -> dict[str, list[Instrument]]:
    """Drop farthest-from-ATM strikes per stock until the universe fits."""
    budget = config.UNIVERSE_CAPACITY - len(futures)
    log.info("Universe %d > capacity %d - trimming far-OTM strikes "
             "(option budget %d)", total, config.UNIVERSE_CAPACITY, budget)

    anchors = _futures_ltp(kite, futures)
    n_opts = sum(len(c) for c in chain_rows.values())
    keep_ratio = budget / n_opts

    trimmed: dict[str, list[Instrument]] = {}
    for sym, chain in chain_rows.items():
        anchor = anchors.get(sym)
        if anchor is None:
            strikes = sorted({c.strike for c in chain})
            anchor = strikes[len(strikes) // 2]
        keep_n = max(10, int(len(chain) * keep_ratio))
        ordered = sorted(chain, key=lambda c: abs(c.strike - anchor))
        kept = ordered[:keep_n]
        trimmed[sym] = kept
    kept_total = sum(len(c) for c in trimmed.values())
    log.info("Trimmed options: %d -> %d contracts", n_opts, kept_total)
    return trimmed


def save_universe_csv(uni: Universe, path: Path | None = None) -> Path:
    config.ensure_dirs()
    path = path or (config.META_DIR /
                    f"{date.today().isoformat()}_universe.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["token", "tradingsymbol", "underlying", "kind",
                    "strike", "lot_size", "expiry"])
        for i in uni.instruments:
            w.writerow([i.token, i.tradingsymbol, i.underlying, i.kind,
                        i.strike, i.lot_size, i.expiry.isoformat()])
    log.info("Universe snapshot saved: %s", path)
    return path


def load_universe_csv(path: Path) -> Universe:
    """Rebuild a Universe from a saved snapshot (used by replay)."""
    uni = Universe()
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            uni.instruments.append(Instrument(
                token=int(row["token"]),
                tradingsymbol=row["tradingsymbol"],
                underlying=row["underlying"],
                kind=row["kind"],
                strike=float(row["strike"]),
                lot_size=int(row["lot_size"]),
                expiry=datetime.strptime(row["expiry"], "%Y-%m-%d").date(),
            ))
    uni.finalize()
    return uni


if __name__ == "__main__":
    logging.basicConfig(level=config.LOG_LEVEL, format="%(levelname)s %(message)s")
    from auth import get_kite
    kite = get_kite(interactive=True)
    symbols = config.load_stock_list()
    print(f"Building universe for {len(symbols)} stocks...")
    uni = build_universe(kite, symbols)
    save_universe_csv(uni)
    per_stock: dict[str, int] = {}
    for inst in uni.instruments:
        per_stock[inst.underlying] = per_stock.get(inst.underlying, 0) + 1
    print(f"\n{'Stock':<15}{'Contracts':>10}")
    for sym in sorted(per_stock):
        print(f"{sym:<15}{per_stock[sym]:>10}")
    print(f"\nTotal instruments: {len(uni.instruments)} "
          f"(capacity {config.UNIVERSE_CAPACITY})")
    if uni.missing_symbols:
        print(f"NOT FOUND in NFO: {', '.join(uni.missing_symbols)}")
