"use client";
import { memo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import clsx from "clsx";
import type { OneWayMover } from "@/lib/types";
import { TrendingUp, TrendingDown, Gauge, Crown, ChevronDown, Flame, AlertTriangle } from "lucide-react";

interface Props { movers: OneWayMover[]; exits?: OneWayMover[] }

const FADE_T = { duration: 0.12 };

function fmtTime(iso?: string | null) {
  if (!iso) return "-";
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}
function fmtPrice(p: number) {
  return p >= 10000
    ? p.toLocaleString("en-IN", { maximumFractionDigits: 0 })
    : p.toLocaleString("en-IN", { maximumFractionDigits: 1 });
}

function tvUrl(sym: string) {
  return `https://www.tradingview.com/chart/?symbol=NSE%3A${encodeURIComponent(sym.replace(/[-&]/g, "_"))}`;
}

function TvLink({ sym, className }: { sym: string; className: string }) {
  return (
    <a
      href={tvUrl(sym)}
      target="_blank"
      rel="noopener noreferrer"
      title={`Open ${sym} on TradingView`}
      className={clsx(className, "hover:text-amber-DEFAULT hover:underline")}
    >
      {sym}
    </a>
  );
}

function contractInfo(m: OneWayMover) {
  const c = m.contract.split(" ")[0];
  const wall =
    (m.direction === "BUY" && c.endsWith("PE")) ||
    (m.direction === "SELL" && c.endsWith("CE"));
  return { c, wall };
}

const REGIME_STYLE: Record<string, string> = {
  TREND: "bg-green-soft text-green-DEFAULT",
  MIXED: "bg-amber-DEFAULT/15 text-amber-DEFAULT",
  CHOP: "bg-red-soft text-red-DEFAULT",
};

function SizeChip({ m }: { m: OneWayMover }) {
  const s = m.size ?? 1;
  if (s >= 1) return null;
  return (
    <span className="rounded bg-faint/60 px-1 py-px font-mono text-2xs text-muted">
      size ×{s.toFixed(1)}
    </span>
  );
}

function FuelGauge({ m }: { m: OneWayMover }) {
  const forced = m.fuel_forced_cr ?? 0;
  const spec = m.fuel_spec_cr ?? 0;
  const tot = forced + spec;
  if (tot <= 0) return null;
  const fPct = Math.round((forced / tot) * 100);
  return (
    <div className="mt-1.5">
      <div className="flex items-center justify-between font-mono text-2xs text-muted">
        <span className="flex items-center gap-1">
          <Flame className="h-2.5 w-2.5 text-amber-DEFAULT" />
          fuel · forced {fPct}% / fresh {100 - fPct}%
        </span>
        <span>{tot.toFixed(1)}cr / 30m</span>
      </div>
      <div className="mt-0.5 flex h-1.5 w-full overflow-hidden rounded-full bg-faint/40">
        <div className="h-full bg-amber-DEFAULT/80" style={{ width: `${fPct}%` }} />
        <div className="h-full bg-blue-DEFAULT/60" style={{ width: `${100 - fPct}%` }} />
      </div>
    </div>
  );
}

function TopCard({ m }: { m: OneWayMover }) {
  const up = m.direction === "BUY";
  const winning = m.pnl_pct >= 0;
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={FADE_T}
      className="rounded-xl border border-amber-DEFAULT/40 border-l-2 border-l-amber-DEFAULT bg-amber-DEFAULT/5 p-4"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="inline-flex items-center gap-1 rounded-md bg-amber-DEFAULT/20 px-2 py-0.5 text-2xs font-bold uppercase tracking-wide text-amber-DEFAULT">
            <Crown className="h-3 w-3" /> Conviction {fmtTime(m.conv_ts)}
          </span>
          <span className={clsx(
            "inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-2xs font-bold",
            up ? "bg-green-soft text-green-DEFAULT" : "bg-red-soft text-red-DEFAULT"
          )}>
            {up ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
            {up ? "UP" : "DOWN"}
          </span>
          {m.stalling && (
            <span className="rounded bg-amber-DEFAULT/15 px-1.5 py-0.5 text-2xs font-semibold uppercase text-amber-DEFAULT">
              stalling
            </span>
          )}
        </div>
        <span className={clsx(
          "rounded-md px-2 py-0.5 font-mono text-sm font-bold tabular-nums",
          winning ? "bg-green-soft text-green-DEFAULT" : "bg-red-soft text-red-DEFAULT"
        )}>
          {winning ? "+" : ""}{m.pnl_pct.toFixed(2)}%
        </span>
      </div>

      <div className="mt-2 flex items-baseline justify-between gap-2">
        <TvLink sym={m.underlying} className="truncate text-lg font-bold text-text" />
        <span className="font-mono text-sm font-semibold tabular-nums text-text">
          ₹{fmtPrice(m.last_price)}
        </span>
      </div>

      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 font-mono text-2xs tabular-nums text-muted">
        <span>in {fmtTime(m.entry_ts)} @ ₹{fmtPrice(m.entry_price)}</span>
        {(m.stop_px ?? 0) > 0 && <span>stop ₹{fmtPrice(m.stop_px!)}</span>}
        <span>day {m.price_pct_day >= 0 ? "+" : ""}{m.price_pct_day.toFixed(1)}%</span>
        <ContractChip m={m} up={up} />
        <SizeChip m={m} />
      </div>

      <FuelGauge m={m} />
      <ExitRiskRow risk={m.exit_risk ?? 0} />
    </motion.div>
  );
}

function ContractChip({ m, up }: { m: OneWayMover; up: boolean }) {
  const { c, wall } = contractInfo(m);
  if (!c) return null;
  return (
    <span className="inline-flex items-center gap-1">
      <span className={clsx("font-semibold", up ? "text-green-DEFAULT" : "text-red-DEFAULT")}>
        {c}
      </span>
      {wall && (
        <span className="rounded bg-amber-DEFAULT/15 px-1 py-px text-amber-DEFAULT">
          writer wall - don&apos;t buy this leg
        </span>
      )}
    </span>
  );
}

function PromoBar({ pct }: { pct: number }) {
  const p = Math.max(0, Math.min(100, pct));
  const near = p >= 85;                          // about to promote
  return (
    <div className="mt-1.5" title="Fills as the ride meets the promotion legs (P&L ≥1%, survived 30m, fresh high, aligned flow). 100% = promotes to Top Board.">
      <div className="mb-0.5 flex items-center justify-between font-mono text-2xs tabular-nums">
        <span className="uppercase tracking-wide text-faint">
          {near ? "promoting →" : "→ Top Board"}
        </span>
        <span className={clsx("font-bold", near ? "text-green-DEFAULT" : "text-muted")}>
          {Math.round(p)}%
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-faint/40">
        <div
          className={clsx(
            "h-full rounded-full transition-[width] duration-500 ease-out",
            near ? "bg-green-DEFAULT motion-safe:animate-pulse" : "bg-green-DEFAULT/70"
          )}
          style={{ width: `${p}%` }}
        />
      </div>
    </div>
  );
}

function ExitRiskRow({ risk }: { risk: number }) {
  const r = Math.max(0, Math.min(100, risk));
  if (r < 40) return null;                        // only surface when it matters
  const hot = r >= 70;
  return (
    <div className="mt-1 flex items-center gap-1.5 font-mono text-2xs tabular-nums"
         title="How close this ride is to being removed (nearest of: retest stop, hard stop, ride-trail give-back, or the 15:00 close).">
      <AlertTriangle className={clsx("h-2.5 w-2.5 shrink-0", hot ? "text-red-DEFAULT" : "text-amber-DEFAULT")} />
      <span className="uppercase tracking-wide text-faint">exit risk</span>
      <div className="h-1 flex-1 overflow-hidden rounded-full bg-faint/40">
        <div className={clsx("h-full rounded-full transition-[width] duration-500", hot ? "bg-red-DEFAULT" : "bg-amber-DEFAULT")}
             style={{ width: `${r}%` }} />
      </div>
      <span className={clsx("font-bold", hot ? "text-red-DEFAULT" : "text-amber-DEFAULT")}>{Math.round(r)}%</span>
    </div>
  );
}

function ProbeCard({ m }: { m: OneWayMover }) {
  const up = m.direction === "BUY";
  const winning = m.pnl_pct >= 0;
  const badge = m.kind === "nr" || m.kind === "loader" || m.kind === "squeeze";
  const late = badge && m.prime_window === false;
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: late ? 0.45 : 1 }}
      exit={{ opacity: 0 }}
      transition={FADE_T}
      className={clsx(
        "rounded-xl border bg-surface p-3 transition-colors duration-200 hover:bg-cardHover",
        late ? "border-border" : up ? "border-green-DEFAULT/25" : "border-red-DEFAULT/25"
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          <span className={clsx(
            "inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-2xs font-bold",
            up ? "bg-green-soft text-green-DEFAULT" : "bg-red-soft text-red-DEFAULT"
          )}>
            {up ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
            {up ? "UP" : "DOWN"}
          </span>
          <TvLink sym={m.underlying} className="truncate text-sm font-bold text-text" />
          <span className="inline-flex items-center gap-0.5 rounded bg-faint/60 px-1 py-px font-mono text-2xs text-muted">
            <Gauge className="h-2.5 w-2.5" />{Math.round(m.score)}
          </span>
          {badge && (
            <span className={clsx(
              "rounded px-1 py-px font-mono text-2xs font-semibold uppercase",
              m.kind === "squeeze"
                ? "bg-purple-500/15 text-purple-400"
                : "bg-blue-soft text-blue-DEFAULT"
            )}>
              {m.kind === "loader" ? "loader" : m.kind === "squeeze" ? "squeeze" : "NR"}
            </span>
          )}
          {late && (
            <span className="rounded bg-faint/60 px-1 py-px font-mono text-2xs text-muted">
              late - historically 0/12
            </span>
          )}
        </div>
        <div className="flex shrink-0 items-baseline gap-1.5">
          <span className="font-mono text-xs font-semibold tabular-nums text-text">
            ₹{fmtPrice(m.last_price)}
          </span>
          <span className={clsx(
            "rounded px-1 py-px font-mono text-2xs font-bold tabular-nums",
            winning ? "bg-green-soft text-green-DEFAULT" : "bg-red-soft text-red-DEFAULT"
          )}>
            {winning ? "+" : ""}{m.pnl_pct.toFixed(2)}%
          </span>
        </div>
      </div>

      <div className="mt-1 flex items-center gap-1 font-mono text-2xs tabular-nums text-muted">
        <span>in {fmtTime(m.entry_ts)} @ ₹{fmtPrice(m.entry_price)}</span>
        <span className="text-faint">·</span>
        <ContractChip m={m} up={up} />
        {(m.stop_px ?? 0) > 0 && (
          <>
            <span className="text-faint">·</span>
            <span>stop ₹{fmtPrice(m.stop_px!)}</span>
          </>
        )}
        <span className="ml-auto">day {m.price_pct_day >= 0 ? "+" : ""}{m.price_pct_day.toFixed(1)}%</span>
      </div>

      <div className="mt-1 flex flex-wrap items-center gap-1 font-mono text-2xs tabular-nums">
        <span className="rounded bg-blue-soft px-1 py-px font-semibold text-blue-DEFAULT">
          {m.build_x.toFixed(0)}× build
        </span>
        <span className="rounded bg-faint/50 px-1 py-px text-muted">{Math.round(m.dominance * 100)}% one-sided</span>
        <span className="rounded bg-faint/50 px-1 py-px text-muted">{Math.round(m.clean_flow * 100)}% clean</span>
        {m.two_sided > 0.3 && (
          <span className="rounded bg-amber-DEFAULT/15 px-1 py-px text-amber-DEFAULT">two-sided {Math.round(m.two_sided * 100)}%</span>
        )}
        <SizeChip m={m} />
      </div>

      <PromoBar pct={m.promo_pct ?? 0} />
      <ExitRiskRow risk={m.exit_risk ?? 0} />
    </motion.div>
  );
}

function MinorRow({ m }: { m: OneWayMover }) {
  const up = m.direction === "BUY";
  const winning = m.pnl_pct >= 0;
  return (
    <div className="flex items-center gap-2 rounded-lg border border-border/60 bg-surface/60 px-2.5 py-1.5 font-mono text-2xs tabular-nums text-muted">
      <span className={clsx("font-bold", up ? "text-green-DEFAULT" : "text-red-DEFAULT")}>
        {up ? "▲" : "▼"}
      </span>
      <TvLink sym={m.underlying} className="font-semibold text-text" />
      <span>{m.kind}</span>
      <span>in {fmtTime(m.entry_ts)}</span>
      {(m.promo_pct ?? 0) > 5 && (
        <span className={clsx("rounded px-1 py-px", (m.promo_pct ?? 0) >= 85 ? "bg-green-soft font-bold text-green-DEFAULT" : "text-faint")}
              title="Readiness to promote to the Top Board">
          →TB {Math.round(m.promo_pct ?? 0)}%
        </span>
      )}
      {(m.exit_risk ?? 0) >= 60 && (
        <span className="rounded bg-red-soft px-1 py-px text-red-DEFAULT" title="Close to removal">
          exit {Math.round(m.exit_risk ?? 0)}%
        </span>
      )}
      <span className={clsx("ml-auto font-bold", winning ? "text-green-DEFAULT" : "text-red-DEFAULT")}>
        {winning ? "+" : ""}{m.pnl_pct.toFixed(2)}%
      </span>
    </div>
  );
}

function OneWayMovers({ movers, exits = [] }: Props) {
  const [showStopped, setShowStopped] = useState(false);
  const promoted = movers.filter(m => m.conviction)
    .sort((a, b) => b.pnl_pct - a.pnl_pct);
  const probes = movers.filter(m => !m.conviction && (m.kind === "nr" || m.kind === "loader" || m.kind === "squeeze"))
    .sort((a, b) => Number(b.prime_window ?? true) - Number(a.prime_window ?? true) || b.score - a.score);
  const minors = movers.filter(m => !m.conviction && m.kind !== "nr" && m.kind !== "loader" && m.kind !== "squeeze")
    .sort((a, b) => b.score - a.score);
  const latest = [...movers].sort((a, b) => b.ts.localeCompare(a.ts))[0];
  const regime = latest?.regime;

  return (
    <section className="flex flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-card">
      <div className="flex items-center justify-between gap-2 border-b border-border px-5 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="text-sm font-bold text-text">Conviction Funnel</span>
          {regime && (
            <span className={clsx(
              "shrink-0 rounded-md px-1.5 py-0.5 font-mono text-2xs font-bold uppercase",
              REGIME_STYLE[regime] ?? REGIME_STYLE.MIXED
            )}>
              {regime === "TREND" ? "trend day" : regime === "CHOP" ? "chop day - protect" : "mixed day"}
            </span>
          )}
          <span className="hidden truncate text-2xs text-muted sm:inline">
            probes fire 09:25-10:20 · survivors promote themselves ~10:30-11:00 · size only the Top Board
          </span>
        </div>
        <span className="shrink-0 rounded-sm bg-amber-DEFAULT/15 px-2 py-0.5 font-mono text-2xs uppercase tracking-wide text-amber-DEFAULT">
          top board {promoted.length} · probes {probes.length + minors.length}
        </span>
      </div>

      {/* ---------------- TOP BOARD ---------------- */}
      <div className="border-b border-border p-3">
        <div className="mb-2 flex items-center gap-1.5 px-1 text-2xs font-semibold uppercase tracking-widest text-amber-DEFAULT">
          <Crown className="h-3.5 w-3.5" /> Top Board - conviction rides
        </div>
        {promoted.length === 0 ? (
          <div className="rounded-xl border border-dashed border-amber-DEFAULT/30 px-3 py-6 text-center text-2xs text-muted">
            No conviction ride yet - probes are testing themselves
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            <AnimatePresence initial={false} mode="popLayout">
              {promoted.map(m => <TopCard key={m.underlying} m={m} />)}
            </AnimatePresence>
          </div>
        )}
      </div>

      {/* ---------------- PROBES ---------------- */}
      <div className="border-b border-border p-3">
        <div className="mb-2 px-1 text-2xs font-semibold uppercase tracking-widest text-muted">
          Probes - badge entries testing themselves (small size or watch-only)
        </div>
        {probes.length === 0 && (
          <div className="rounded-xl border border-dashed border-border px-3 py-4 text-center text-2xs text-muted">
            No open probes
          </div>
        )}
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          <AnimatePresence initial={false} mode="popLayout">
            {probes.map(m => <ProbeCard key={m.underlying} m={m} />)}
          </AnimatePresence>
        </div>
        {minors.length > 0 && (
          <div className="mt-2 grid gap-1 md:grid-cols-2 xl:grid-cols-3">
            {minors.map(m => <MinorRow key={m.underlying} m={m} />)}
          </div>
        )}
      </div>

      <button
        type="button"
        onClick={() => setShowStopped(v => !v)}
        className="flex w-full items-center justify-between px-5 py-2.5 text-left text-2xs font-semibold text-muted transition-colors hover:bg-cardHover"
      >
        <span>Stopped / closed today ({exits.length})</span>
        <ChevronDown className={clsx("h-3.5 w-3.5 transition-transform", showStopped && "rotate-180")} />
      </button>
      {showStopped && exits.length > 0 && (
        <div className="grid gap-1 px-3 pb-3 md:grid-cols-2">
          {exits.map((m, i) => (
            <div key={`${m.underlying}-${m.entry_ts}-${i}`}
              className="flex items-center gap-2 rounded-lg bg-surface/50 px-2.5 py-1.5 font-mono text-2xs tabular-nums text-muted">
              <span className={clsx("font-bold", m.direction === "BUY" ? "text-green-DEFAULT" : "text-red-DEFAULT")}>
                {m.direction === "BUY" ? "▲" : "▼"}
              </span>
              <span className="font-semibold text-text">{m.underlying}</span>
              <span>{m.kind}</span>
              <span className="truncate">{m.note}</span>
              <span className={clsx("ml-auto shrink-0 font-bold",
                m.pnl_pct >= 0 ? "text-green-DEFAULT" : "text-red-DEFAULT")}>
                {m.pnl_pct >= 0 ? "+" : ""}{m.pnl_pct.toFixed(2)}%
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export default memo(OneWayMovers);
