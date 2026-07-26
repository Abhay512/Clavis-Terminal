export type Side = "BUY_SIDE" | "SELL_SIDE" | "";
export type Classification =
  | "LONG_BUILDUP"
  | "SHORT_BUILDUP"
  | "SHORT_COVERING"
  | "LONG_UNWINDING"
  | "NEUTRAL";

export interface Signal {
  ts: string;
  token: number;
  tradingsymbol: string;
  underlying: string;
  kind: "FUT" | "CE" | "PE";
  strike: number;
  expiry: string;
  oi_now: number;
  oi_delta: number;
  oi_pct: number;
  zscore: number;
  price: number;
  price_pct: number;
  volume: number;
  classification: Classification;
  side: Side;
  underlying_price: number;
  notional_cr: number;
  score: number;
  intrabar: boolean;
  monitored_min?: number;      // minutes this contract has been watched
}

export interface StockRank {
  ts: string;
  underlying: string;
  fut_price: number;
  price_pct_day: number;
  fut_classification: Classification;
  buy_units: number;
  sell_units: number;
  buy_notional_cr: number;
  sell_notional_cr: number;
  ce_buy_cr: number;
  pe_buy_cr: number;
  ce_write_cr: number;
  pe_write_cr: number;
  ce_cover_cr: number;         // call short-covering (bullish exit fuel)
  pe_cover_cr: number;         // put short-covering  (bearish exit fuel)
  ce_unwind_cr: number;        // call long-unwinding (bearish)
  pe_unwind_cr: number;        // put long-unwinding  (bullish)
  top_buy_strike: string;
  top_sell_strike: string;
  top_ce_buy_strike: string;
  top_pe_buy_strike: string;
}

export interface BigPlayerSignal {
  ts: string;
  underlying: string;
  direction: "BUY" | "SELL";     // bullish / bearish near-spot positioning
  strength: number;              // 0-100
  near_dom: number;              // one-sidedness of near-spot OI (0-1)
  net_cr: number;                // signed near-spot net flow (Rs cr)
  fut_price: number;
  price_pct_day: number;
  ce_strike: string;             // strongest CE contribution, e.g. "1200CE +45k"
  pe_strike: string;
  n_strikes: number;             // near-spot strikes showing a build
  first_seen: string;
  monitored_min?: number;
  note: string;
}

export interface OneWayMover {
  ts: string;
  underlying: string;
  direction: "BUY" | "SELL";     // BUY = one-way UP, SELL = one-way DOWN
  status: "ENTRY" | "OPEN" | "EXIT";
  score: number;                 // 0-100
  entry_ts: string;
  entry_price: number;
  last_price: number;
  pnl_pct: number;               // signed WITH the call (+ = winning)
  price_pct_day: number;
  build_x: number;               // cum flow / the stock's own typical flow
  dominance: number;             // recent one-sidedness of the money (0-1)
  clean_flow: number;            // price efficiency 0-1 (clean = high)
  retrace_pct: number;           // realized pullback / move (0-1)
  two_sided: number;             // OI both-sides ratio now (0-1)
  cum_net_cr: number;
  monitored_min?: number;
  contract: string;
  note: string;                  // exit reason
  reasons: string[];
  kind?: "normal" | "fast" | "nr" | "loader" | "squeeze";  // entry path
  prime_window?: boolean;        // entered <= 10:20 (9/9 winners did;
  //                                12/12 later badges lost/scratched)
  conviction?: boolean;          // promoted to the Top Board (sticky)
  conv_ts?: string | null;       // promotion time
  stalling?: boolean;            // no fresh extreme >20m (hint, not a demote)
  stop_px?: number;              // live stop level (buffered retest px)
  fuel_forced_cr?: number;       // rolling 30m: writing+covering+opp-unwind
  fuel_spec_cr?: number;         // rolling 30m: fresh trend-side buying
  regime?: "TREND" | "MIXED" | "CHOP";  // day type when the ride opened
  size?: number;                 // advisory position-size multiplier
  promo_pct?: number;            // 0-100 energy bar: probe readiness for Top Board
  exit_risk?: number;            // 0-100: how close this ride is to removal
}

export interface OIMultipleRow {
  ts: string;
  underlying: string;
  running_max: number;           // highest near-spot OI multiple today (2x..119x)
  contract: string;              // strike that set it, e.g. "530PE"
  base_oi: number;
  peak_oi: number;
  t_max: string;                 // when the max printed
  first_2x: string | null;       // first minute any near-spot strike hit 2x
  strikes_2x: number;
  direction: "BUY" | "SELL" | "MIXED";  // premium overlay read
  dominance: number;             // 0.5 = mixed, 1 = one-sided
  bull_cr: number;
  bear_cr: number;
  top_writer: boolean;           // top strike's premium fell = writers
  fresh: string;                 // biggest near-zero-base build, "540CE +4050k"
  fut_price: number;
  price_pct_day: number;
  monitored_min?: number;
  counter_tape?: boolean;        // fades a broadly one-way tape - unreliable
  //                                (07-08 BUY 42%, 07-09 SELL 33%); greyed
}

export interface PositionBuild {
  ts: string;
  underlying: string;
  direction: "BUY" | "SELL";
  phase: "LOADED" | "BUILDING" | "MOVING";
  score: number;               // 0-100
  cum_net_cr: number;          // signed cumulative 4-way net flow (Rs cr)
  cum_total_cr: number;
  dominance: number;           // 0-1
  persistence: number;         // 0-1
  fut_price: number;
  price_pct_day: number;
  first_seen: string;
  breakout_ts?: string | null; // position -> move moment (null = pending)
  monitored_min?: number;
  ce_wall: string;             // biggest CE OI build today
  pe_wall: string;
  note: string;
}

export interface SectorLeader {
  ts: string;
  sector: string;                 // POWER, BANK, IT, PHARMA, ...
  sector_strength: number;        // directional strength of the sector, %
  sector_rank: number;            // 1 = strongest sector on the board
  underlying: string;
  direction: "BUY" | "SELL";      // BUY = leading an up sector, SELL = down
  move_pct: number;               // the leader's own move-from-open, signed
  rank_in_sector: number;         // 1 = sector's strongest one-way leader
  fut_price: number;
  breakout_ts: string | null;     // first minute it crossed the breakout move
  locked: boolean;                // true on the daily SL_DECISION snapshot
}

export interface ScreenerStatus {
  market_open: boolean;
  instruments: number;
  signals_today: number;
  server_time?: string;
  connected_at?: string;
  feed_down?: boolean;   // tick feed silent, watchdog reconnects failing
  feed_note?: string;
}

export type WsMessage =
  | { type: "signal";   data: Signal }
  | { type: "ranking";  data: StockRank[] }
  | { type: "position"; data: PositionBuild[] }
  | { type: "oneway";   data: OneWayMover[] }
  | { type: "radar";    data: BigPlayerSignal[] }
  | { type: "oimult";   data: OIMultipleRow[] }
  | { type: "sector";   data: SectorLeader[] }
  | { type: "history";  data: Signal[] }
  | { type: "status";   data: ScreenerStatus };
