"use client";
import { memo } from "react";
import MarketClock from "./MarketClock";
import ConnectionDot from "./ConnectionDot";
import type { ScreenerStatus } from "@/lib/types";
import { Activity } from "lucide-react";

interface Props {
  status: ScreenerStatus;
  wsStatus: "connecting" | "connected" | "reconnecting" | "offline";
  demo?: boolean;
}

function Header({ status, wsStatus, demo }: Props) {
  const live = !demo && wsStatus === "connected" && !!status.market_open;
  return (
    <header className="sticky top-0 z-40 h-14 border-b border-border bg-bg">
      <div className="flex h-full items-center justify-between px-5">
        {/* Logo - amber brand accent (Bloomberg tone) */}
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-DEFAULT/10">
            <Activity className="h-4 w-4 text-amber-DEFAULT" strokeWidth={2.5} />
          </div>
          <div>
            <p className="text-sm font-bold uppercase leading-none tracking-[0.14em] text-amber-DEFAULT">Clavis Terminal</p>
            <p className="mt-0.5 text-2xs tracking-wider text-muted">The key to understand F&amp;O markets.</p>
          </div>
        </div>

        {/* Center: instruments */}
        <div className="hidden items-center gap-6 sm:flex">
          <Stat label="Instruments" value={status.instruments?.toLocaleString() ?? "-"} />
          <div className="h-4 w-px bg-border" />
          <Stat label="Signals today" value={String(status.signals_today ?? 0)} highlight />
        </div>

        {/* Right: clock + connection + LIVE badge */}
        <div className="flex items-center gap-4">
          <MarketClock />
          <div className="h-4 w-px bg-border" />
          <ConnectionDot status={wsStatus} demo={demo} />
          {live && (
            <>
              <div className="h-4 w-px bg-border" />
              <span className="inline-flex items-center gap-1.5 rounded-sm border border-red-DEFAULT/40 bg-red-soft px-2.5 py-1">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-DEFAULT opacity-60" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-red-DEFAULT" />
                </span>
                <span className="text-2xs font-bold uppercase tracking-[0.18em] text-red-DEFAULT">
                  Live
                </span>
              </span>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

function Stat({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="text-center">
      <p className={`font-mono text-sm font-semibold tabular-nums ${highlight ? "text-amber-DEFAULT" : "text-text"}`}>
        {value}
      </p>
      <p className="text-2xs text-muted">{label}</p>
    </div>
  );
}

export default memo(Header);
