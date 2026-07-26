import type { Signal, StockRank, ScreenerStatus, PositionBuild, OneWayMover, BigPlayerSignal, OIMultipleRow, SectorLeader, Classification } from "./types";

export const MOCK_STATUS: ScreenerStatus = {
  market_open: true,
  instruments: 8_240,
  signals_today: 47,
  server_time: new Date().toISOString(),
};

interface RankSeed {
  u: string; price: number; day: number; cls: string;
  buyCr: number; sellCr: number;
  ceBuy: number; peBuy: number; ceWrite: number; peWrite: number;
  topBuy: string; topSell: string; topCeBuy: string; topPeBuy: string;
}

const SEEDS: RankSeed[] = [
  { u: "RELIANCE",   price: 1442.5,  day:  1.8, cls: "LONG_BUILDUP",  buyCr: 17.3, sellCr:  6.5, ceBuy: 14.1, peBuy: 3.2, ceWrite: 1.5, peWrite: 5.0, topBuy: "1450CE +120000", topSell: "1420PE +80000",  topCeBuy: "1450CE +120000", topPeBuy: "1420PE +21000" },
  { u: "HDFCBANK",   price: 1780.2,  day: -1.2, cls: "SHORT_BUILDUP", buyCr: 13.9, sellCr: 19.6, ceBuy: 2.9,  peBuy: 11.0, ceWrite: 15.6, peWrite: 4.0, topBuy: "1750PE +110000", topSell: "1800CE +130000", topCeBuy: "1800CE +18000",  topPeBuy: "1750PE +110000" },
  { u: "TCS",        price: 3580.0,  day:  0.9, cls: "LONG_BUILDUP",  buyCr: 11.4, sellCr:  7.5, ceBuy: 9.0,  peBuy: 2.4, ceWrite: 2.5, peWrite: 5.0, topBuy: "3600CE +32000",  topSell: "3500PE +21000",  topCeBuy: "3600CE +32000",  topPeBuy: "3550PE +8000" },
  { u: "INFY",       price: 1660.4,  day:  1.1, cls: "LONG_BUILDUP",  buyCr:  9.1, sellCr:  2.7, ceBuy: 7.8,  peBuy: 1.3, ceWrite: 0.7, peWrite: 2.0, topBuy: "1680CE +64000",  topSell: "1640PE +19000",  topCeBuy: "1680CE +64000",  topPeBuy: "1640PE +6000" },
  { u: "SBIN",       price:  792.6,  day: -0.8, cls: "SHORT_BUILDUP", buyCr:  3.2, sellCr: 12.2, ceBuy: 0.8,  peBuy: 2.4, ceWrite: 9.8, peWrite: 2.4, topBuy: "780PE +87000",   topSell: "800CE +95000",   topCeBuy: "800CE +9000",    topPeBuy: "780PE +87000" },
  { u: "BAJFINANCE", price: 6800.0,  day:  2.4, cls: "LONG_BUILDUP",  buyCr:  7.5, sellCr:  4.9, ceBuy: 6.2,  peBuy: 1.3, ceWrite: 1.1, peWrite: 3.8, topBuy: "6900CE +11000",  topSell: "6700PE +7200",   topCeBuy: "6900CE +11000",  topPeBuy: "6700PE +2100" },
  { u: "AXISBANK",   price: 1124.8,  day:  0.1, cls: "NEUTRAL",       buyCr:  6.1, sellCr:  5.8, ceBuy: 3.1,  peBuy: 3.0, ceWrite: 2.9, peWrite: 2.9, topBuy: "1140CE +41000",  topSell: "1100PE +39000",  topCeBuy: "1140CE +41000",  topPeBuy: "1110PE +22000" },
  { u: "ICICIBANK",  price: 1280.9,  day:  1.5, cls: "LONG_BUILDUP",  buyCr:  8.7, sellCr:  2.7, ceBuy: 7.2,  peBuy: 1.5, ceWrite: 0.8, peWrite: 1.9, topBuy: "1300CE +52000",  topSell: "1260PE +16000",  topCeBuy: "1300CE +52000",  topPeBuy: "1260PE +5000" },
  { u: "LT",         price: 3700.3,  day: -1.9, cls: "SHORT_BUILDUP", buyCr:  3.3, sellCr: 12.6, ceBuy: 0.6,  peBuy: 2.7, ceWrite: 10.2, peWrite: 2.4, topBuy: "3650PE +34000",  topSell: "3750CE +42000",  topCeBuy: "3750CE +4000",   topPeBuy: "3650PE +34000" },
  { u: "MARUTI",     price: 12800.0, day:  0.6, cls: "LONG_BUILDUP",  buyCr:  5.4, sellCr:  3.6, ceBuy: 4.4,  peBuy: 1.0, ceWrite: 1.2, peWrite: 2.4, topBuy: "13000CE +4200",  topSell: "12500PE +2800",  topCeBuy: "13000CE +4200",  topPeBuy: "12500PE +900" },
];

export const MOCK_RANKINGS: StockRank[] = SEEDS.map((s) => ({
  ts: new Date().toISOString(),
  underlying: s.u,
  fut_price: s.price,
  price_pct_day: s.day,
  fut_classification: s.cls as Classification,
  buy_units: Math.round((s.buyCr * 1e7) / s.price),
  sell_units: Math.round((s.sellCr * 1e7) / s.price),
  buy_notional_cr: s.buyCr,
  sell_notional_cr: s.sellCr,
  ce_buy_cr: s.ceBuy,
  pe_buy_cr: s.peBuy,
  ce_write_cr: s.ceWrite,
  pe_write_cr: s.peWrite,
  ce_cover_cr: +(s.buyCr * 0.08).toFixed(2),
  pe_cover_cr: +(s.sellCr * 0.06).toFixed(2),
  ce_unwind_cr: +(s.sellCr * 0.05).toFixed(2),
  pe_unwind_cr: +(s.buyCr * 0.07).toFixed(2),
  top_buy_strike: s.topBuy,
  top_sell_strike: s.topSell,
  top_ce_buy_strike: s.topCeBuy,
  top_pe_buy_strike: s.topPeBuy,
}));

const _mins = (n: number) => new Date(Date.now() - n * 60_000).toISOString();

export const MOCK_RADAR: BigPlayerSignal[] = [
  { ts: new Date().toISOString(), underlying: "COFORGE",  direction: "BUY",  strength: 100, near_dom: 1.00, net_cr:  39, fut_price: 1465.0, price_pct_day: 0.7, ce_strike: "1460CE +225k", pe_strike: "1340PE +3k",  n_strikes: 14, first_seen: _mins(41), note: "" },
  { ts: new Date().toISOString(), underlying: "ASHOKLEY", direction: "SELL", strength: 82,  near_dom: 1.00, net_cr: -21, fut_price: 158.4,  price_pct_day: 0.4, ce_strike: "170CE +175k",  pe_strike: "160PE +135k", n_strikes: 16, first_seen: _mins(36), note: "" },
  { ts: new Date().toISOString(), underlying: "DRREDDY",  direction: "SELL", strength: 73,  near_dom: 1.00, net_cr: -18, fut_price: 6280.0, price_pct_day: -1.4, ce_strike: "1320CE +28k", pe_strike: "1320PE +31k", n_strikes: 12, first_seen: _mins(61), note: "" },
  { ts: new Date().toISOString(), underlying: "HCLTECH",  direction: "BUY",  strength: 51,  near_dom: 1.00, net_cr:  13, fut_price: 1142.0, price_pct_day: -0.4, ce_strike: "1140CE +89k", pe_strike: "1050PE +2k",  n_strikes: 10, first_seen: _mins(15), note: "" },
];

export const MOCK_ONEWAY: OneWayMover[] = [
  { ts: new Date().toISOString(), underlying: "NAUKRI",   direction: "BUY",  status: "OPEN", score: 78, entry_ts: _mins(52), entry_price: 1082.0, last_price: 1131.5, pnl_pct: 4.58, price_pct_day: 8.9, build_x: 21, dominance: 0.86, clean_flow: 0.62, retrace_pct: 0.19, two_sided: 0.08, cum_net_cr: 268.0, monitored_min: 62, contract: "1120CE +25850", note: "", reasons: ["21x its own typical flow", "86% one-sided (last 15m)", "price 62% efficient (clean)", "money still coming in"], kind: "nr", prime_window: true, conviction: true, conv_ts: _mins(20), stalling: false, stop_px: 1094.5, fuel_forced_cr: 9.2, fuel_spec_cr: 3.4 },
  { ts: new Date().toISOString(), underlying: "TVSMOTOR",  direction: "BUY",  status: "OPEN", score: 66, entry_ts: _mins(31), entry_price: 2810.0, last_price: 2856.5, pnl_pct: 1.66, price_pct_day: 2.1, build_x: 12, dominance: 0.72, clean_flow: 0.54, retrace_pct: 0.30, two_sided: 0.11, cum_net_cr: 44.0,  monitored_min: 96, contract: "2850CE +9200",  note: "", reasons: ["12x its own typical flow", "72% one-sided (last 15m)", "price 54% efficient (clean)"], kind: "loader", prime_window: true, conviction: false, stop_px: 2801.0 },
  { ts: new Date().toISOString(), underlying: "BIOCON",    direction: "SELL", status: "OPEN", score: 62, entry_ts: _mins(24), entry_price: 421.0,  last_price: 412.2,  pnl_pct: 2.09, price_pct_day: -3.1, build_x: 34, dominance: 0.84, clean_flow: 0.51, retrace_pct: 0.25, two_sided: 0.13, cum_net_cr: -138.0, monitored_min: 88, contract: "410PE +26400",  note: "", reasons: ["34x its own typical flow", "84% one-sided (last 15m)", "price 51% efficient (clean)", "money still coming in"], kind: "nr", prime_window: false, conviction: false, stop_px: 424.1 },
  { ts: new Date().toISOString(), underlying: "PIDILITIND",direction: "SELL", status: "OPEN", score: 60, entry_ts: _mins(15), entry_price: 2940.0, last_price: 2903.0, pnl_pct: 1.26, price_pct_day: -2.3, build_x: 18, dominance: 0.79, clean_flow: 0.48, retrace_pct: 0.30, two_sided: 0.20, cum_net_cr: -52.0, monitored_min: 75, contract: "2900PE +4100",  note: "", reasons: ["18x its own typical flow", "79% one-sided (last 15m)", "price 48% efficient (clean)"], kind: "normal" },
];

export const MOCK_OIMULT: OIMultipleRow[] = [
  { ts: new Date().toISOString(), underlying: "KALYANKJIL", running_max: 119.0, contract: "530PE", base_oi: 5400,  peak_oi: 642600, t_max: _mins(10), first_2x: _mins(240), strikes_2x: 9, direction: "BUY",  dominance: 1.0,  bull_cr: 96.2, bear_cr: 0.4,  top_writer: true,  fresh: "540CE +4048k", fut_price: 505.4, price_pct_day: 7.6 },
  { ts: new Date().toISOString(), underlying: "MPHASIS",    running_max: 26.2,  contract: "2400CE", base_oi: 11200, peak_oi: 293400, t_max: _mins(35), first_2x: _mins(250), strikes_2x: 6, direction: "BUY",  dominance: 0.94, bull_cr: 41.0, bear_cr: 2.5,  top_writer: false, fresh: "", fut_price: 2874.0, price_pct_day: 3.0 },
  { ts: new Date().toISOString(), underlying: "ICICIGI",    running_max: 15.9,  contract: "1700CE", base_oi: 8300,  peak_oi: 132000, t_max: _mins(60), first_2x: _mins(230), strikes_2x: 4, direction: "SELL", dominance: 0.91, bull_cr: 1.9,  bear_cr: 19.8, top_writer: true,  fresh: "", fut_price: 1693.5, price_pct_day: -2.3 },
  { ts: new Date().toISOString(), underlying: "ASTRAL",     running_max: 11.7,  contract: "1460PE", base_oi: 9100,  peak_oi: 106500, t_max: _mins(75), first_2x: _mins(180), strikes_2x: 3, direction: "SELL", dominance: 0.86, bull_cr: 2.2,  bear_cr: 13.6, top_writer: false, fresh: "", fut_price: 1447.2, price_pct_day: -0.5 },
  { ts: new Date().toISOString(), underlying: "TRENT",      running_max: 6.3,   contract: "2866CE", base_oi: 15200, peak_oi: 95800,  t_max: _mins(20), first_2x: _mins(210), strikes_2x: 2, direction: "MIXED", dominance: 0.55, bull_cr: 8.1, bear_cr: 6.6,  top_writer: true,  fresh: "", fut_price: 5980.0, price_pct_day: -0.3 },
];

export const MOCK_SECTOR: SectorLeader[] = [
  { ts: new Date().toISOString(), sector: "RETAIL",  sector_strength:  4.10, sector_rank: 1, underlying: "KALYANKJIL", direction: "BUY",  move_pct:  7.60, rank_in_sector: 1, breakout_ts: _mins(55), fut_price:  505.4, locked: false },
  { ts: new Date().toISOString(), sector: "RETAIL",  sector_strength:  4.10, sector_rank: 1, underlying: "TRENT",      direction: "BUY",  move_pct:  1.84, rank_in_sector: 2, breakout_ts: _mins(40), fut_price: 5980.0, locked: false },
  { ts: new Date().toISOString(), sector: "PHARMA",  sector_strength:  2.90, sector_rank: 2, underlying: "LAURUSLABS", direction: "BUY",  move_pct:  3.30, rank_in_sector: 1, breakout_ts: _mins(55), fut_price: 1447.2, locked: false },
  { ts: new Date().toISOString(), sector: "PHARMA",  sector_strength:  2.90, sector_rank: 2, underlying: "ALKEM",      direction: "BUY",  move_pct:  1.90, rank_in_sector: 2, breakout_ts: _mins(40), fut_price: 5271.0, locked: false },
  { ts: new Date().toISOString(), sector: "FMCG",    sector_strength: -2.40, sector_rank: 3, underlying: "PATANJALI",  direction: "SELL", move_pct: -3.10, rank_in_sector: 1, breakout_ts: _mins(55), fut_price:  365.0, locked: false },
  { ts: new Date().toISOString(), sector: "FMCG",    sector_strength: -2.40, sector_rank: 3, underlying: "COLPAL",     direction: "SELL", move_pct: -1.60, rank_in_sector: 2, breakout_ts: _mins(40), fut_price: 2095.0, locked: false },
  { ts: new Date().toISOString(), sector: "POWER",   sector_strength:  2.10, sector_rank: 4, underlying: "ADANIPOWER", direction: "BUY",  move_pct:  2.80, rank_in_sector: 1, breakout_ts: _mins(55), fut_price:  224.6, locked: false },
  { ts: new Date().toISOString(), sector: "POWER",   sector_strength:  2.10, sector_rank: 4, underlying: "JSWENERGY",  direction: "BUY",  move_pct:  1.50, rank_in_sector: 2, breakout_ts: _mins(40), fut_price:  557.0, locked: false },
  { ts: new Date().toISOString(), sector: "FINANCE", sector_strength:  1.70, sector_rank: 5, underlying: "ANGELONE",   direction: "BUY",  move_pct:  2.20, rank_in_sector: 1, breakout_ts: _mins(55), fut_price: 2874.0, locked: false },
  { ts: new Date().toISOString(), sector: "FINANCE", sector_strength:  1.70, sector_rank: 5, underlying: "CDSL",       direction: "BUY",  move_pct:  1.30, rank_in_sector: 2, breakout_ts: _mins(40), fut_price: 1693.5, locked: false },
  { ts: new Date().toISOString(), sector: "IT",      sector_strength:  1.40, sector_rank: 6, underlying: "KPITTECH",   direction: "BUY",  move_pct:  1.80, rank_in_sector: 1, breakout_ts: _mins(55), fut_price: 1442.5, locked: false },
  { ts: new Date().toISOString(), sector: "IT",      sector_strength:  1.40, sector_rank: 6, underlying: "MPHASIS",    direction: "BUY",  move_pct:  1.10, rank_in_sector: 2, breakout_ts: _mins(40), fut_price: 2874.0, locked: false },
];

export const MOCK_POSITION: PositionBuild[] = [
  { ts: new Date().toISOString(), underlying: "RELIANCE",  direction: "BUY",  phase: "MOVING",   score: 96, cum_net_cr:  212.4, cum_total_cr: 305.0, dominance: 0.70, persistence: 0.77, fut_price: 1442.5, price_pct_day:  1.8, first_seen: _mins(95), breakout_ts: _mins(60), monitored_min: 120, ce_wall: "1500CE +820k", pe_wall: "1400PE +610k", note: "breakout 10:44" },
  { ts: new Date().toISOString(), underlying: "TRENT",     direction: "SELL", phase: "LOADED",   score: 78, cum_net_cr: -148.9, cum_total_cr: 410.2, dominance: 0.36, persistence: 0.67, fut_price: 5980.0, price_pct_day: -0.2, first_seen: _mins(70), breakout_ts: null,      monitored_min: 120, ce_wall: "6000CE +112k", pe_wall: "5900PE +48k",  note: "position built, price quiet - watch coming sessions" },
  { ts: new Date().toISOString(), underlying: "HDFCBANK",  direction: "SELL", phase: "BUILDING", score: 64, cum_net_cr:  -86.1, cum_total_cr: 190.3, dominance: 0.45, persistence: 0.62, fut_price: 1780.2, price_pct_day: -0.6, first_seen: _mins(40), breakout_ts: null,      monitored_min: 120, ce_wall: "1800CE +240k", pe_wall: "1760PE +90k",  note: "" },
];


let _signalId = 0;
export function makeMockSignal(partial?: Partial<Signal>): Signal {
  const sides = ["BUY_SIDE", "SELL_SIDE"] as const;
  const underlyings = ["RELIANCE", "HDFCBANK", "TCS", "INFY", "SBIN", "BAJFINANCE"];
  const u = underlyings[_signalId % underlyings.length];
  const side = sides[_signalId % 2];
  const kind = side === "BUY_SIDE" ? "CE" : "PE";
  const score = Math.floor(60 + Math.random() * 40);
  const oi_pct = +(5 + Math.random() * 15).toFixed(1);
  const oi_delta = Math.floor(10000 + Math.random() * 90000);
  _signalId++;
  return {
    ts: new Date().toISOString(),
    token: 1000 + _signalId,
    tradingsymbol: `${u}26JUL${1400 + _signalId * 50}${kind}`,
    underlying: u, kind, strike: 1400 + _signalId * 50,
    expiry: "2026-07-31", oi_now: 500_000 + oi_delta,
    oi_delta, oi_pct, zscore: +(3 + Math.random() * 5).toFixed(1),
    price: +(20 + Math.random() * 80).toFixed(2),
    price_pct: side === "BUY_SIDE" ? +Math.abs(Math.random() * 2).toFixed(2) : -(Math.random() * 2).toFixed(2) as unknown as number,
    volume: oi_delta + Math.floor(Math.random() * 5000),
    classification: side === "BUY_SIDE" ? "LONG_BUILDUP" : "SHORT_BUILDUP",
    side, underlying_price: 1440,
    notional_cr: +(oi_delta * 1440 / 1e7).toFixed(2),
    score, intrabar: Math.random() > 0.7,
    ...partial,
  };
}
