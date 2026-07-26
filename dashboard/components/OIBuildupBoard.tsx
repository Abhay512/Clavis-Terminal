"use client";
import { memo } from "react";
import clsx from "clsx";
import type { OIMultipleRow } from "@/lib/types";
import { Layers, TrendingUp, TrendingDown, PenLine, ArrowUpRight, Sparkles } from "lucide-react";

interface Props { rows: OIMultipleRow[] }

function fmtTime(iso?: string | null) {
  if (!iso) return "-";
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function Row({ r, i }: { r: OIMultipleRow; i: number }) {
  const buy = r.direction === "BUY";
  return (
    <div className={clsx(
      "flex items-center gap-2 border-b border-border/40 px-2 py-1.5 last:border-0",
      r.counter_tape && "opacity-40"
    )}>
      <span className="w-4 shrink-0 text-right font-mono text-2xs text-faint">{i + 1}</span>
      <span className="w-24 shrink-0 truncate text-xs font-bold text-text">
        {r.underlying}
        {r.counter_tape && (
          <span className="ml-1 rounded bg-amber-DEFAULT/15 px-1 py-px font-mono text-2xs font-normal text-amber-DEFAULT">
            counter-tape
          </span>
        )}
      </span>
      <span className={clsx(
        "shrink-0 rounded px-1.5 py-px font-mono text-xs font-bold tabular-nums",
        buy ? "bg-green-soft text-green-DEFAULT" : "bg-red-soft text-red-DEFAULT"
      )}>
        {r.running_max >= 100 ? r.running_max.toFixed(0) : r.running_max.toFixed(1)}×
      </span>
      <span className="inline-flex shrink-0 items-center gap-0.5 rounded bg-faint/50 px-1 py-px font-mono text-2xs text-muted">
        {r.contract}
        {r.top_writer
          ? <PenLine className="h-2.5 w-2.5" aria-label="writers" />
          : <ArrowUpRight className="h-2.5 w-2.5" aria-label="buyers" />}
      </span>
      {r.fresh && (
        <span className="hidden shrink-0 items-center gap-0.5 rounded bg-amber-DEFAULT/15 px-1 py-px font-mono text-2xs text-amber-DEFAULT xl:inline-flex">
          <Sparkles className="h-2.5 w-2.5" />{r.fresh}
        </span>
      )}
      <span className="ml-auto shrink-0 font-mono text-2xs tabular-nums text-muted">
        2x {fmtTime(r.first_2x)}
      </span>
      <span className="hidden w-12 shrink-0 sm:block">
        <span className="block h-1 w-full overflow-hidden rounded-full bg-faint/40">
          <span
            className={clsx("block h-full", buy ? "bg-green-DEFAULT/70" : "bg-red-DEFAULT/70")}
            style={{ width: `${Math.round(r.dominance * 100)}%` }}
          />
        </span>
      </span>
      <span className={clsx(
        "w-14 shrink-0 text-right font-mono text-2xs font-bold tabular-nums",
        r.price_pct_day >= 0 ? "text-green-DEFAULT" : "text-red-DEFAULT"
      )}>
        {r.price_pct_day >= 0 ? "+" : ""}{r.price_pct_day.toFixed(1)}%
      </span>
    </div>
  );
}

function Board({ rows, buy }: { rows: OIMultipleRow[]; buy: boolean }) {
  return (
    <div className="min-w-0 flex-1">
      <div className={clsx(
        "flex items-center gap-1.5 px-2 pb-1 text-2xs font-semibold uppercase tracking-widest",
        buy ? "text-green-DEFAULT" : "text-red-DEFAULT"
      )}>
        {buy ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
        {buy ? "BUY-side builds" : "SELL-side builds"} ({rows.length})
      </div>
      {rows.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-2xs text-muted">
          No one-sided {buy ? "bullish" : "bearish"} builds ≥2× yet
        </div>
      ) : rows.map((r, i) => <Row key={r.underlying} r={r} i={i} />)}
    </div>
  );
}

function OIBuildupBoard({ rows }: Props) {
  const buys = rows.filter(r => r.direction === "BUY");
  const sells = rows.filter(r => r.direction === "SELL");
  const mixed = rows.filter(r => r.direction === "MIXED");
  return (
    <section className="flex flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-card">
      <div className="flex items-center justify-between gap-2 border-b border-border px-5 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <Layers className="h-4 w-4 shrink-0 text-blue-DEFAULT" />
          <span className="text-sm font-bold text-text">OI Build-up Multiples</span>
          <span className="hidden truncate text-2xs text-muted lg:inline">
            near-spot OI × its open baseline · magnitude ranks, 2× alone means nothing · squeeze moves (OI falling) invisible here
          </span>
        </div>
        <span className="shrink-0 rounded-sm bg-faint/60 px-2 py-0.5 font-mono text-2xs uppercase tracking-wide text-muted">
          watch only
        </span>
      </div>
      <div className="flex flex-col gap-3 p-3 lg:flex-row">
        <Board rows={buys} buy />
        <Board rows={sells} buy={false} />
      </div>
      {mixed.length > 0 && (
        <div className="border-t border-border/60 px-3 py-2">
          <span className="font-mono text-2xs text-faint">
            mixed (two-sided, no clean call):{" "}
            {mixed.map(r => `${r.underlying} ${r.running_max.toFixed(1)}×`).join(" · ")}
          </span>
        </div>
      )}
    </section>
  );
}

export default memo(OIBuildupBoard);
