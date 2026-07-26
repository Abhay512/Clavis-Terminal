"use client";
import { memo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import clsx from "clsx";
import type { BigPlayerSignal } from "@/lib/types";
import { Radar, ArrowUpRight, ArrowDownRight } from "lucide-react";

interface Props { signals: BigPlayerSignal[] }

const FADE_T = { duration: 0.12 };

function fmtTime(iso: string) {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}
function fmtPrice(p: number) {
  return p >= 10000
    ? p.toLocaleString("en-IN", { maximumFractionDigits: 0 })
    : p.toLocaleString("en-IN", { maximumFractionDigits: 1 });
}

function BigPlayerRadar({ signals }: Props) {
  return (
    <section className="flex flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-card">
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <Radar className="h-4 w-4 shrink-0 text-amber-DEFAULT" />
          <span className="truncate text-sm font-semibold text-text">Big Player Radar</span>
          <span className="hidden truncate text-2xs text-muted sm:inline">
            OI at the ±10 strikes around spot - where institutions are positioning right now
          </span>
        </div>
        <span className="shrink-0 rounded-sm bg-faint/60 px-2 py-0.5 font-mono text-2xs uppercase tracking-wide text-muted">
          near-spot OI
        </span>
      </div>

      <div className="px-2 py-1.5">
        {signals.length === 0 && (
          <div className="flex min-h-16 items-center justify-center px-4 text-center text-xs text-muted">
            Reading the near-spot option chain. Stocks appear when the OI at the
            strikes around spot builds strongly one direction.
          </div>
        )}
        <AnimatePresence initial={false} mode="popLayout">
          {signals.map((s) => {
            const buy = s.direction === "BUY";
            const dayUp = s.price_pct_day >= 0;
            return (
              <motion.div
                key={s.underlying}
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
                      buy ? "bg-green-soft text-green-DEFAULT" : "bg-red-soft text-red-DEFAULT"
                    )}>
                      {buy ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
                      {buy ? "BULL" : "BEAR"}
                    </span>
                    <span className="truncate text-xs font-semibold text-text">{s.underlying}</span>
                    <span className="rounded bg-amber-DEFAULT/15 px-1 py-px font-mono text-2xs font-semibold text-amber-DEFAULT">
                      {Math.round(s.strength)}
                    </span>
                    <span className="hidden font-mono text-2xs text-faint sm:inline">since {fmtTime(s.first_seen)}</span>
                  </div>
                  <div className="flex shrink-0 items-baseline gap-1.5">
                    <span className="font-mono text-xs font-semibold tabular-nums text-text">
                      ₹{fmtPrice(s.fut_price)}
                    </span>
                    <span className={clsx(
                      "font-mono text-2xs font-medium tabular-nums",
                      dayUp ? "text-green-DEFAULT" : "text-red-DEFAULT"
                    )}>
                      {dayUp ? "+" : ""}{s.price_pct_day.toFixed(1)}%
                    </span>
                  </div>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-1 font-mono text-2xs tabular-nums text-muted">
                  <span className={clsx("font-semibold", buy ? "text-green-DEFAULT" : "text-red-DEFAULT")}>
                    ₹{Math.abs(s.net_cr).toFixed(0)}cr near-spot
                  </span>
                  <span className="text-faint">·</span>
                  <span>{Math.round(s.near_dom * 100)}% one-sided</span>
                  <span className="text-faint">·</span>
                  <span>{s.n_strikes} strikes</span>
                  <span className="ml-auto hidden truncate pl-2 sm:inline">
                    {s.ce_strike && <span className="text-green-DEFAULT/80">{s.ce_strike}</span>}
                    {s.ce_strike && s.pe_strike && <span className="text-faint"> / </span>}
                    {s.pe_strike && <span className="text-red-DEFAULT/80">{s.pe_strike}</span>}
                  </span>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </section>
  );
}

export default memo(BigPlayerRadar);
