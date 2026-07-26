"use client";
import { memo, useMemo } from "react";
import clsx from "clsx";
import type { SectorLeader } from "@/lib/types";
import { Boxes, TrendingUp, TrendingDown, Zap } from "lucide-react";

interface Props { rows: SectorLeader[] }

interface SectorGroup {
  sector: string;
  strength: number;
  rank: number;
  buy: boolean;
  leaders: SectorLeader[];
}

function fmtTime(iso?: string | null) {
  if (!iso) return null;
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function toGroups(rows: SectorLeader[]): SectorGroup[] {
  const by = new Map<string, SectorGroup>();
  for (const r of rows) {
    let g = by.get(r.sector);
    if (!g) {
      g = { sector: r.sector, strength: r.sector_strength, rank: r.sector_rank,
            buy: r.direction === "BUY", leaders: [] };
      by.set(r.sector, g);
    }
    g.leaders.push(r);
  }
  for (const g of by.values())
    g.leaders.sort((a, b) => a.rank_in_sector - b.rank_in_sector);
  return [...by.values()].sort((a, b) => a.rank - b.rank);
}

function SectorBars({ groups }: { groups: SectorGroup[] }) {
  const max = Math.max(0.5, ...groups.map(g => Math.abs(g.strength)));
  return (
    <div className="border-b border-border/60 px-3 py-3">
      <div className="mb-2 flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-widest text-muted">
        <Zap className="h-3 w-3" /> sector strength
      </div>
      <div className="flex flex-col gap-1">
        {groups.map(g => (
          <div key={g.sector} className="flex items-center gap-2">
            <span className={clsx(
              "w-20 shrink-0 truncate text-2xs font-bold uppercase tracking-wide",
              g.buy ? "text-green-DEFAULT" : "text-red-DEFAULT"
            )}>
              {g.sector}
            </span>
            <span className="relative flex h-3.5 flex-1 items-center overflow-hidden rounded-sm bg-faint/25">
              <span
                className={clsx(
                  "block h-full rounded-sm transition-all",
                  g.buy ? "bg-green-DEFAULT/80" : "bg-red-DEFAULT/80"
                )}
                style={{ width: `${Math.round((Math.abs(g.strength) / max) * 100)}%` }}
              />
            </span>
            <span className={clsx(
              "w-14 shrink-0 text-right font-mono text-2xs font-bold tabular-nums",
              g.buy ? "text-green-DEFAULT" : "text-red-DEFAULT"
            )}>
              {g.strength >= 0 ? "+" : ""}{g.strength.toFixed(1)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function LeaderRow({ r, buy }: { r: SectorLeader; buy: boolean }) {
  const brk = fmtTime(r.breakout_ts);
  return (
    <div className="flex items-center gap-2 px-2 py-1">
      <span className="w-3 shrink-0 text-right font-mono text-2xs text-faint">{r.rank_in_sector}</span>
      <span className="w-24 shrink-0 truncate text-xs font-bold text-text">{r.underlying}</span>
      <span className={clsx(
        "shrink-0 rounded px-1.5 py-px font-mono text-2xs font-bold uppercase tracking-wide",
        buy ? "bg-green-soft text-green-DEFAULT" : "bg-red-soft text-red-DEFAULT"
      )}>
        {r.direction}
      </span>
      {brk && (
        <span className="hidden shrink-0 items-center gap-0.5 rounded bg-faint/50 px-1 py-px font-mono text-2xs text-muted sm:inline-flex">
          <Zap className="h-2.5 w-2.5" />brk {brk}
        </span>
      )}
      <span className="ml-auto shrink-0 font-mono text-2xs tabular-nums text-muted">
        ₹{r.fut_price >= 1000 ? r.fut_price.toFixed(0) : r.fut_price.toFixed(1)}
      </span>
      <span className={clsx(
        "w-14 shrink-0 text-right font-mono text-2xs font-bold tabular-nums",
        r.move_pct >= 0 ? "text-green-DEFAULT" : "text-red-DEFAULT"
      )}>
        {r.move_pct >= 0 ? "+" : ""}{r.move_pct.toFixed(1)}%
      </span>
    </div>
  );
}

function SectorCard({ g }: { g: SectorGroup }) {
  const mag = Math.min(Math.abs(g.strength) / 5, 1); // 5% = full bar
  return (
    <div className={clsx(
      "min-w-0 rounded-lg border border-l-4 bg-bg/40",
      g.buy ? "border-border/60 border-l-green-DEFAULT/70" : "border-border/60 border-l-red-DEFAULT/70"
    )}>
      <div className={clsx(
        "flex items-center gap-2 border-b border-border/40 px-2 py-1.5",
        g.buy ? "bg-green-soft/40" : "bg-red-soft/40"
      )}>
        <span className="w-4 shrink-0 text-right font-mono text-2xs text-faint">#{g.rank}</span>
        <span className={clsx(
          "shrink-0 text-xs font-bold uppercase tracking-wide",
          g.buy ? "text-green-DEFAULT" : "text-red-DEFAULT"
        )}>{g.sector}</span>
        {g.buy
          ? <TrendingUp className="h-3 w-3 shrink-0 text-green-DEFAULT" />
          : <TrendingDown className="h-3 w-3 shrink-0 text-red-DEFAULT" />}
        <span className="ml-auto shrink-0 w-16">
          <span className="block h-1 w-full overflow-hidden rounded-full bg-faint/40">
            <span
              className={clsx("block h-full", g.buy ? "bg-green-DEFAULT/70" : "bg-red-DEFAULT/70")}
              style={{ width: `${Math.round(mag * 100)}%` }}
            />
          </span>
        </span>
        <span className={clsx(
          "w-14 shrink-0 text-right font-mono text-2xs font-bold tabular-nums",
          g.buy ? "text-green-DEFAULT" : "text-red-DEFAULT"
        )}>
          {g.strength >= 0 ? "+" : ""}{g.strength.toFixed(1)}%
        </span>
      </div>
      {g.leaders.map(r => <LeaderRow key={r.underlying} r={r} buy={g.buy} />)}
    </div>
  );
}

function SectorLeaders({ rows }: Props) {
  const groups = useMemo(() => toGroups(rows), [rows]);

  return (
    <section className="flex flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-card">
      <div className="flex items-center justify-between gap-2 border-b border-border px-5 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <Boxes className="h-4 w-4 shrink-0 text-blue-DEFAULT" />
          <span className="text-sm font-bold text-text">Sector Leaders</span>
          <span className="hidden truncate text-2xs text-muted lg:inline">
            strongest sectors × their one-way leaders · pick the sector, take its leader · contained the target 71% in backtest
          </span>
        </div>
        <span className="shrink-0 rounded-sm bg-faint/60 px-2 py-0.5 font-mono text-2xs uppercase tracking-wide text-muted">
          shadow · watch only
        </span>
      </div>
      {groups.length === 0 ? (
        <div className="m-3 rounded-lg border border-dashed border-border px-3 py-6 text-center text-2xs text-muted">
          No sector leaders yet - building as the session develops (best ~10:45)
        </div>
      ) : (
        <>
          <SectorBars groups={groups} />
          <div className="flex flex-col gap-2 p-3">
            {groups.map(g => <SectorCard key={g.sector} g={g} />)}
          </div>
        </>
      )}
    </section>
  );
}

export default memo(SectorLeaders);
