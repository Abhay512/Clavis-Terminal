"use client";
import { memo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import clsx from "clsx";
import RankBar from "./RankBar";
import type { StockRank } from "@/lib/types";
import { TrendingUp, TrendingDown } from "lucide-react";

interface Props {
  side: "buy" | "sell";
  rows: StockRank[];
  rankingTs: string;
}

const FADE_T = { duration: 0.12 };

function futIcon(cls: string) {
  if (cls === "LONG_BUILDUP" || cls === "SHORT_COVERING")
    return <TrendingUp className="h-3 w-3 text-green-DEFAULT" />;
  if (cls === "SHORT_BUILDUP" || cls === "LONG_UNWINDING")
    return <TrendingDown className="h-3 w-3 text-red-DEFAULT" />;
  return null;
}

function RankingTable({ side, rows, rankingTs }: Props) {
  const isBuy   = side === "buy";
  const color   = isBuy ? "green" : "red";
  const maxCr   = rows[0] ? (isBuy ? rows[0].buy_notional_cr : rows[0].sell_notional_cr) : 1;
  const accent  = isBuy ? "text-green-DEFAULT" : "text-red-DEFAULT";
  const badge   = isBuy
    ? "bg-green-soft text-green-DEFAULT"
    : "bg-red-soft   text-red-DEFAULT";

  return (
    <section className="relative flex flex-col overflow-hidden rounded-2xl border border-border bg-card">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex items-center gap-2.5">
          <span className={`inline-flex items-center gap-1.5 rounded-sm px-2.5 py-1 text-2xs font-semibold uppercase tracking-widest ${badge}`}>
            {isBuy ? "▲ Buy Pressure" : "▼ Sell / Write"}
          </span>
          <span className="text-xs text-muted">Option OI build-up (5 min)</span>
        </div>
        {rankingTs && (
          <span className="font-mono text-2xs text-muted tabular-nums">
            {new Date(rankingTs).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
          </span>
        )}
      </div>

      {/* Column headers */}
      <div className="grid grid-cols-[24px_1.1fr_76px_88px_1fr] gap-x-3 px-5 py-2 text-2xs font-medium uppercase tracking-widest text-muted">
        <span>#</span>
        <span>Stock</span>
        <span className="text-right">₹ crore</span>
        <span className="text-right">LTP / Day</span>
        <span className="pl-2">Top strike</span>
      </div>

      {/* Rows */}
      <div className="flex-1 overflow-y-auto px-3 pb-3">
        {rows.length === 0 && (
          <div className="flex h-48 items-center justify-center text-sm text-muted">
            Waiting for data...
          </div>
        )}
        <AnimatePresence initial={false} mode="popLayout">
          {rows.map((row, i) => {
            const cr = isBuy ? row.buy_notional_cr : row.sell_notional_cr;
            const strike = isBuy ? row.top_buy_strike : row.top_sell_strike;
            const dayUp = (row.price_pct_day ?? 0) >= 0;
            return (
              <motion.div
                key={row.underlying}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={FADE_T}
                className="group mb-1 grid grid-cols-[24px_1.1fr_76px_88px_1fr] items-center gap-x-3 rounded-xl px-2 py-2 transition-colors duration-200 hover:bg-cardHover"
              >
                {/* Rank */}
                <span className="text-center text-xs font-semibold text-muted">{i + 1}</span>

                {/* Stock + bar */}
                <div className="min-w-0">
                  <div className="mb-1 flex items-center gap-1.5">
                    <span className="text-sm font-semibold text-text truncate">{row.underlying}</span>
                    {futIcon(row.fut_classification)}
                  </div>
                  <RankBar value={cr} max={maxCr} color={color} />
                </div>

                {/* ₹ crore */}
                <p className={clsx("text-right font-mono text-sm font-bold tabular-nums", accent)}>
                  {cr.toFixed(1)}
                </p>

                {/* Live price + day % */}
                <div className="text-right">
                  <p className="font-mono text-xs font-semibold tabular-nums text-text">
                    {row.fut_price >= 10000
                      ? row.fut_price.toLocaleString("en-IN", { maximumFractionDigits: 0 })
                      : row.fut_price.toLocaleString("en-IN", { maximumFractionDigits: 1 })}
                  </p>
                  <p className={clsx(
                    "font-mono text-2xs font-medium tabular-nums",
                    dayUp ? "text-green-DEFAULT" : "text-red-DEFAULT"
                  )}>
                    {dayUp ? "+" : ""}{(row.price_pct_day ?? 0).toFixed(1)}%
                  </p>
                </div>

                {/* Strike detail */}
                <p className="truncate pl-2 font-mono text-2xs text-muted">{strike || "-"}</p>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </section>
  );
}

export default memo(RankingTable);
