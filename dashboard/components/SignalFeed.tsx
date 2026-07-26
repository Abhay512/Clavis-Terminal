"use client";
import { memo, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import clsx from "clsx";
import type { Signal } from "@/lib/types";
import { Zap, Clock } from "lucide-react";

interface Props { signals: Signal[] }

function fmt(ts: string) {
  try {
    return new Date(ts).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch { return ts.slice(11, 19) || "-"; }
}

function ScoreBadge({ score }: { score: number }) {
  const cls =
    score >= 80 ? "bg-green-soft text-green-DEFAULT" :
    score >= 60 ? "bg-amber-soft text-amber-DEFAULT" :
                  "bg-faint text-muted";
  return <span className={`rounded-sm px-2 py-0.5 font-mono text-2xs font-bold tabular-nums ${cls}`}>{score}</span>;
}

function SideBadge({ side, kind }: { side: string; kind: string }) {
  if (side === "BUY_SIDE")  return <span className="rounded-md bg-green-soft px-2 py-0.5 text-2xs font-bold text-green-DEFAULT">BUY</span>;
  if (side === "SELL_SIDE") return <span className="rounded-md bg-red-soft   px-2 py-0.5 text-2xs font-bold text-red-DEFAULT">WRITE</span>;
  if (kind === "FUT")       return <span className="rounded-md bg-blue-soft  px-2 py-0.5 text-2xs font-bold text-blue-DEFAULT">FUT</span>;
  return null;
}

const ITEM = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: 0.12 } },
  exit:    { opacity: 0, transition: { duration: 0.1 } },
};

function SignalFeed({ signals }: Props) {
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }, [signals.length]);

  return (
    <section className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-card">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex items-center gap-2">
          <Zap className="h-4 w-4 text-amber-DEFAULT" />
          <span className="text-sm font-semibold text-text">Live Signal Feed</span>
        </div>
        <span className="rounded-sm bg-faint px-2.5 py-0.5 font-mono text-2xs font-bold text-muted">
          {signals.length}
        </span>
      </div>

      {/* Feed */}
      <div ref={listRef} className="flex-1 overflow-y-auto px-3 pb-3 pt-2">
        {signals.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-2 py-16 text-center">
            <Clock className="h-8 w-8 text-faint" />
            <p className="text-sm text-muted">Waiting for spikes...</p>
            <p className="text-2xs text-faint">Signals appear here in real time</p>
          </div>
        )}
        <AnimatePresence initial={false} mode="popLayout">
          {signals.map((s) => {
            const isBuy  = s.side === "BUY_SIDE";
            const isSell = s.side === "SELL_SIDE";
            const borderCls = isBuy  ? "border-l-green-DEFAULT" :
                              isSell ? "border-l-red-DEFAULT"   : "border-l-blue-DEFAULT";
            const contract = s.kind === "FUT"
              ? "FUT"
              : `${s.strike % 1 === 0 ? s.strike : s.strike.toFixed(1)}${s.kind}`;
            return (
              <motion.div
                key={`${s.ts}-${s.token}`}
                variants={ITEM}
                initial="initial"
                animate="animate"
                exit="exit"
                className={clsx(
                  "mb-2 rounded-xl border-l-2 bg-surface px-3.5 py-3 transition-colors duration-150 hover:bg-cardHover",
                  borderCls
                )}
              >
                {/* Row 1: stock + contract + side badge */}
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="font-semibold text-text text-sm">{s.underlying}</span>
                    <span className="font-mono text-2xs text-muted shrink-0">{contract}</span>
                    {s.intrabar && (
                      <span className="rounded bg-faint px-1 py-0.5 text-2xs text-muted">TICK</span>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <SideBadge side={s.side} kind={s.kind} />
                    <ScoreBadge score={s.score} />
                  </div>
                </div>

                {/* Row 2: metrics */}
                <div className="flex items-center gap-3 text-2xs text-muted">
                  <span className={clsx("font-mono font-semibold tabular-nums", isBuy ? "text-green-DEFAULT" : isSell ? "text-red-DEFAULT" : "text-blue-DEFAULT")}>
                    {s.oi_pct > 0 ? "+" : ""}{s.oi_pct.toFixed(1)}% OI
                  </span>
                  <span className="font-mono tabular-nums">z={s.zscore.toFixed(1)}</span>
                  <span className="font-mono tabular-nums">₹{s.notional_cr.toFixed(1)}cr</span>
                  <span className="ml-auto font-mono tabular-nums">{fmt(s.ts)}</span>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </section>
  );
}

export default memo(SignalFeed);
