"""Shadow board: leaders of the strongest NSE sector indices. Trades nothing.

Reference implementation. The production board's sector-strength weighting and
leader qualification are not published; this version scores a sector by the
mean move of its members and takes the strongest names inside it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import config
from engine.market_state import MarketState

log = logging.getLogger("sector")


SECTOR_MAP: dict[str, str] = {
    # Power / Utilities
    "ADANIPOWER": "POWER", "ADANIGREEN": "POWER", "ADANIENSOL": "POWER", "NTPC": "POWER",
    "POWERGRID": "POWER", "TATAPOWER": "POWER", "JSWENERGY": "POWER", "NHPC": "POWER",
    "PREMIERENE": "POWER", "CGPOWER": "POWER", "SUZLON": "POWER", "IREDA": "POWER",
    "INOXWIND": "POWER",
    # Oil & Gas / Energy
    "COALINDIA": "ENERGY", "ONGC": "ENERGY", "BPCL": "ENERGY", "HINDPETRO": "ENERGY",
    "GAIL": "ENERGY", "PETRONET": "ENERGY", "IOC": "ENERGY", "RELIANCE": "ENERGY",
    # Banks
    "BANKBARODA": "BANK", "SBIN": "BANK", "PNB": "BANK", "CANBK": "BANK", "AXISBANK": "BANK",
    "ICICIBANK": "BANK", "HDFCBANK": "BANK", "KOTAKBANK": "BANK", "INDUSINDBK": "BANK",
    "FEDERALBNK": "BANK", "BANKINDIA": "BANK", "AUBANK": "BANK", "IDFCFIRSTB": "BANK",
    "BANDHANBNK": "BANK", "RBLBANK": "BANK", "UNIONBANK": "BANK", "INDIANB": "BANK",
    # NBFC / Finance / Capital markets
    "PNBHOUSING": "FINANCE", "BAJFINANCE": "FINANCE", "CHOLAFIN": "FINANCE",
    "BAJAJFINSV": "FINANCE", "MUTHOOTFIN": "FINANCE", "MANAPPURAM": "FINANCE",
    "SBICARD": "FINANCE", "PFC": "FINANCE", "RECLTD": "FINANCE", "LTF": "FINANCE",
    "SHRIRAMFIN": "FINANCE", "CDSL": "FINANCE", "BSE": "FINANCE", "ANGELONE": "FINANCE",
    "MCX": "FINANCE", "IEX": "FINANCE", "KFINTECH": "FINANCE", "CAMS": "FINANCE",
    "NUVAMA": "FINANCE", "ABCAPITAL": "FINANCE", "PAYTM": "FINANCE", "POLICYBZR": "FINANCE",
    "JIOFIN": "FINANCE", "HDFCAMC": "FINANCE", "LICI": "FINANCE", "SBILIFE": "FINANCE",
    "HDFCLIFE": "FINANCE", "ICICIPRULI": "FINANCE", "ICICIGI": "FINANCE", "MFSL": "FINANCE",
    # IT
    "TCS": "IT", "INFY": "IT", "WIPRO": "IT", "HCLTECH": "IT", "TECHM": "IT", "LTM": "IT",
    "LTIM": "IT", "COFORGE": "IT", "PERSISTENT": "IT", "MPHASIS": "IT", "TATAELXI": "IT",
    "KPITTECH": "IT", "OFSS": "IT",
    # Pharma / Healthcare
    "SUNPHARMA": "PHARMA", "DRREDDY": "PHARMA", "CIPLA": "PHARMA", "DIVISLAB": "PHARMA",
    "ALKEM": "PHARMA", "LAURUSLABS": "PHARMA", "AUROPHARMA": "PHARMA", "BIOCON": "PHARMA",
    "GLENMARK": "PHARMA", "TORNTPHARM": "PHARMA", "ZYDUSLIFE": "PHARMA", "MAXHEALTH": "PHARMA",
    "FORTIS": "PHARMA", "APOLLOHOSP": "PHARMA",
    # Metals
    "HINDZINC": "METAL", "VEDL": "METAL", "HINDALCO": "METAL", "JSWSTEEL": "METAL",
    "TATASTEEL": "METAL", "JINDALSTEL": "METAL", "NATIONALUM": "METAL", "SAIL": "METAL",
    "HINDCOPPER": "METAL",
    # Auto & ancillary
    "MARUTI": "AUTO", "TATAMOTORS": "AUTO", "TMPV": "AUTO", "BAJAJ-AUTO": "AUTO",
    "EICHERMOT": "AUTO", "HEROMOTOCO": "AUTO", "TVSMOTOR": "AUTO", "ASHOKLEY": "AUTO",
    "EXIDEIND": "AUTO", "MOTHERSON": "AUTO", "BOSCHLTD": "AUTO", "UNOMINDA": "AUTO",
    "SONACOMS": "AUTO", "BHARATFORG": "AUTO",
    # FMCG / Consumer staples
    "PATANJALI": "FMCG", "NESTLEIND": "FMCG", "HINDUNILVR": "FMCG", "ITC": "FMCG",
    "BRITANNIA": "FMCG", "DABUR": "FMCG", "COLPAL": "FMCG", "MARICO": "FMCG",
    "GODREJCP": "FMCG", "TATACONSUM": "FMCG",
    # Retail / New-age / Consumer discretionary
    "TRENT": "RETAIL", "DMART": "RETAIL", "NYKAA": "RETAIL", "KALYANKJIL": "RETAIL",
    "TITAN": "RETAIL", "ETERNAL": "RETAIL", "NAUKRI": "RETAIL", "DIXON": "RETAIL",
    # Realty / Infra
    "DLF": "REALTY", "LODHA": "REALTY", "GODREJPROP": "REALTY", "OBEROIRLTY": "REALTY",
    "PRESTIGE": "REALTY", "PHOENIXLTD": "REALTY",
    "ADANIPORTS": "INFRA", "GMRAIRPORT": "INFRA",
    # Capital goods / Industrials
    "SIEMENS": "CAPGOODS", "ABB": "CAPGOODS", "BHEL": "CAPGOODS", "BEL": "CAPGOODS",
    "HAL": "CAPGOODS", "CUMMINSIND": "CAPGOODS", "SUPREMEIND": "CAPGOODS",
    "POLYCAB": "CAPGOODS", "KEI": "CAPGOODS", "KAYNES": "CAPGOODS", "SOLARINDS": "CAPGOODS",
    "MAZDOCK": "CAPGOODS", "RVNL": "CAPGOODS", "HAVELLS": "CAPGOODS", "CROMPTON": "CAPGOODS",
    # Cement
    "AMBUJACEM": "CEMENT", "SHREECEM": "CEMENT", "DALBHARAT": "CEMENT",
    # Chemicals / Paints / Agri
    "ASIANPAINT": "CHEM", "PIDILITIND": "CHEM", "SRF": "CHEM", "PIIND": "CHEM", "UPL": "CHEM",
}


@dataclass(slots=True)
class SectorLeader:
    ts: datetime
    sector: str
    sector_strength: float    # directional strength of the sector, %
    sector_rank: int          # 1 = strongest sector on the board
    underlying: str
    direction: str
    move_pct: float
    rank_in_sector: int       # 1 = the sector's strongest one-way leader
    fut_price: float
    breakout_ts: datetime | None = None  # first minute it crossed SL_BREAKOUT_MOVE
    locked: bool = False      # True on the daily decision snapshot


class SectorLeaders:
    """Groups the futures universe by sector, surfaces each strong sector's one-way
    leaders. Read-only shadow - never opens or closes anything."""

    def __init__(self, market: MarketState):
        self.market = market
        self.locked_board: list[SectorLeader] = []
        self._locked = False
        self._breakout: dict[str, tuple[int, datetime]] = {}

    def _sector_moves(self):
        """{sector: [(move_pct, underlying, fut_price), ...]} for active F&O names."""
        out: dict[str, list] = {}
        for ul, fut in self.market.futures_by_underlying.items():
            sec = SECTOR_MAP.get(ul)
            if sec is None:
                continue
            o = fut.exch_open or fut.day_open
            px = fut.last_price
            if o <= 0 or px <= 0:
                continue
            mv = (px - o) / o * 100.0
            out.setdefault(sec, []).append((mv, ul, px))
        return out

    def _update_breakouts(self, ts: datetime) -> None:
        """First minute a stock crossed SL_BREAKOUT_MOVE in its direction."""
        for ul, fut in self.market.futures_by_underlying.items():
            if ul not in SECTOR_MAP:
                continue
            o = fut.exch_open or fut.day_open
            px = fut.last_price
            if o <= 0 or px <= 0:
                continue
            mv = (px - o) / o * 100.0
            d = 1 if mv >= 0 else -1
            prev = self._breakout.get(ul)
            if abs(mv) >= config.SL_BREAKOUT_MOVE and (prev is None or prev[0] != d):
                self._breakout[ul] = (d, ts)

    def compute(self, ts: datetime) -> list[SectorLeader]:
        """The current sector-leader board. Called every minute."""
        self._update_breakouts(ts)
        moves = self._sector_moves()

        sectors = []
        for sec, members in moves.items():
            if len(members) < config.SL_MIN_SECTOR_MEMBERS:
                continue
            strength = sum(m[0] for m in members) / len(members)
            sectors.append((abs(strength), strength, sec, members))
        sectors.sort(key=lambda x: -x[0])

        board: list[SectorLeader] = []
        for s_rank, (_, strength, sec, members) in enumerate(
                sectors[:config.SL_TOP_SECTORS], 1):
            direction = 1 if strength >= 0 else -1
            leaders = sorted(members, key=lambda m: -m[0] * direction)
            for i, (mv, ul, px) in enumerate(
                    leaders[:config.SL_LEADERS_PER_SECTOR], 1):
                if mv * direction < config.SL_MIN_LEAD_MOVE:
                    continue
                bo = self._breakout.get(ul)
                board.append(SectorLeader(
                    ts=ts, sector=sec, sector_strength=round(strength, 2),
                    sector_rank=s_rank, underlying=ul,
                    direction="BUY" if direction > 0 else "SELL",
                    move_pct=round(mv, 2), rank_in_sector=i, fut_price=px,
                    breakout_ts=bo[1] if (bo and bo[0] == direction) else None))
        return board

    def maybe_lock(self, ts: datetime) -> list[SectorLeader]:
        """At SL_DECISION freeze the day's board; returns it the first time only."""
        if (self._locked or ts.time() < config.SL_DECISION
                or ts.time() > config.MARKET_CLOSE):
            return []
        board = self.compute(ts)
        for r in board:
            r.locked = True
        self.locked_board = board
        self._locked = True
        if board:
            log.info("SECTOR LEADERS (shadow) locked %s: %s", ts.strftime("%H:%M"),
                     ", ".join(f"#{r.sector_rank} {r.sector} {r.direction} "
                               f"{r.underlying}({r.move_pct:+.1f}%)" for r in board))
        return board
