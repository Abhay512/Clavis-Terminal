"use client";
import { memo } from "react";
import type { ScreenerStatus } from "@/lib/types";

interface Props { status: ScreenerStatus; rankingTs: string }

function StatusBar({ status, rankingTs }: Props) {
  const updatedAt = rankingTs
    ? new Date(rankingTs).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : null;

  return (
    <div className="sticky bottom-0 z-40 flex flex-col border-t border-border bg-bg">
      {status.feed_down && (
        <div className="flex items-center gap-2 bg-red-DEFAULT/15 px-5 py-1.5 text-2xs font-semibold text-red-DEFAULT">
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-red-DEFAULT" />
          TICK FEED DOWN - watchdog reconnecting{status.feed_note ? ` · ${status.feed_note}` : ""}
        </div>
      )}
      <div className="flex items-center gap-4 px-4 py-2 font-mono text-2xs text-muted">
      <span>{status.instruments?.toLocaleString() ?? "-"} instruments monitored</span>
      <Sep />
      <span>{status.signals_today ?? 0} signals fired today</span>
      {updatedAt && (
        <>
          <Sep />
          <span>Rankings updated {updatedAt}</span>
        </>
      )}
      <div className="ml-auto text-faint">
        python main.py --api to connect live data
      </div>
      </div>
    </div>
  );
}

function Sep() {
  return <span className="text-faint">·</span>;
}

export default memo(StatusBar);
