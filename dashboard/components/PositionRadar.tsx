"use client";
import { memo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import clsx from "clsx";
import type { PositionBuild } from "@/lib/types";
import { Layers, ArrowUpRight, ArrowDownRight, Zap } from "lucide-react";

interface Props { builds: PositionBuild[] }

const FADE_T = { duration: 0.12 };

function fmtTime(iso?: string | null) {
  if (!iso) return null;
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

const PHASE_STYLE: Record<PositionBuild["phase"], string> = {
  LOADED:   "bg-amber-DEFAULT/15 text-amber-DEFAULT",
  BUILDING: "bg-blue-soft text-blue-DEFAULT",
  MOVING:   "bg-green-soft text-green-DEFAULT",
};

function PositionRadar({ builds }: Props) {
  return (
    <section className="flex flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-card">
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <Layers className="h-4 w-4 shrink-0 text-blue-DEFAULT" />
          <span className="truncate text-sm font-semibold text-text">Position Radar</span>
          <span className="hidden truncate text-2xs text-muted sm:inline">
            where big money is building positions today - LOADED = move likely in coming sessions
          </span>
        </div>
        <span className="shrink-0 rounded-sm bg-faint/60 px-2 py-0.5 font-mono text-2xs uppercase tracking-wide text-muted">
          cumulative flow
        </span>
      </div>

      <div className="px-2 py-1.5">
        {builds.length === 0 && (
          <div className="flex min-h-16 items-center justify-center px-4 text-center text-xs text-muted">
            Accumulating the day&apos;s option-chain money flow per stock. Names
            appear once the cumulative one-sided flow is unmistakable.
          </div>
        )}
        <AnimatePresence initial={false} mode="popLayout">
          {builds.map((b) => {
            const isBuy = b.direction === "BUY";
            const dayUp = b.price_pct_day >= 0;
            const brk = fmtTime(b.breakout_ts);
            return (
              <motion.div
                key={b.underlying}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={FADE_T}
                className="mb-1 rounded-xl px-2.5 py-2 transition-colors duration-200 hover:bg-cardHover"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-1.5">
                    <span className={clsx(
                      "inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-2xs font-bold",
                      isBuy ? "bg-green-soft text-green-DEFAULT" : "bg-red-soft text-red-DEFAULT"
                    )}>
                      {isBuy ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
                      {b.direction}
                    </span>
                    <span className="truncate text-xs font-semibold text-text">{b.underlying}</span>
                    <span className={clsx(
                      "rounded px-1 py-px text-2xs font-semibold uppercase tracking-wide",
                      PHASE_STYLE[b.phase]
                    )}>
                      {b.phase}
                    </span>
                    {brk && (
                      <span className="inline-flex items-center gap-0.5 rounded bg-green-soft px-1 py-px text-2xs font-semibold text-green-DEFAULT">
                        <Zap className="h-2.5 w-2.5" /> {brk}
                      </span>
                    )}
                  </div>
                  <div className="flex shrink-0 items-baseline gap-1.5">
                    <span className="font-mono text-xs font-semibold tabular-nums text-text">
                      {b.fut_price.toLocaleString("en-IN", { maximumFractionDigits: 1 })}
                    </span>
                    <span className={clsx(
                      "font-mono text-2xs font-medium tabular-nums",
                      dayUp ? "text-green-DEFAULT" : "text-red-DEFAULT"
                    )}>
                      {dayUp ? "+" : ""}{b.price_pct_day.toFixed(1)}%
                    </span>
                  </div>
                </div>

                <div className="mt-1 flex items-center gap-1 font-mono text-2xs tabular-nums text-muted">
                  <span className={clsx(
                    "font-semibold",
                    b.cum_net_cr >= 0 ? "text-green-DEFAULT" : "text-red-DEFAULT"
                  )}>
                    ₹{Math.abs(b.cum_net_cr).toFixed(0)}cr {b.cum_net_cr >= 0 ? "bullish" : "bearish"}
                  </span>
                  <span className="text-faint">·</span>
                  <span>{Math.round(b.dominance * 100)}% one-sided</span>
                  <span className="text-faint">·</span>
                  <span>{Math.round(b.persistence * 100)}% persistent</span>
                  {typeof b.monitored_min === "number" && b.monitored_min > 0 && (
                    <>
                      <span className="text-faint">·</span>
                      <span>{b.monitored_min}m watched</span>
                    </>
                  )}
                  <span className="ml-auto hidden truncate pl-2 sm:inline">
                    {b.ce_wall && <span className="text-green-DEFAULT/80">{b.ce_wall}</span>}
                    {b.ce_wall && b.pe_wall && <span className="text-faint"> / </span>}
                    {b.pe_wall && <span className="text-red-DEFAULT/80">{b.pe_wall}</span>}
                  </span>
                </div>
                {b.note && (
                  <p className="mt-0.5 text-2xs text-muted">{b.note}</p>
                )}
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </section>
  );
}

export default memo(PositionRadar);
