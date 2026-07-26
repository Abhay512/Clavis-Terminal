"use client";
import clsx from "clsx";

type Ws = "connecting" | "connected" | "reconnecting" | "offline";

interface Props { status: Ws; demo?: boolean }

const label: Record<Ws, string> = {
  connecting:   "Connecting...",
  connected:    "Connected",
  reconnecting: "Reconnecting...",
  offline:      "Demo",
};
const dot: Record<Ws, string> = {
  connecting:   "bg-amber-DEFAULT animate-pulse-dot",
  connected:    "bg-green-DEFAULT animate-pulse-dot",
  reconnecting: "bg-amber-DEFAULT animate-pulse-dot",
  offline:      "bg-muted",
};

export default function ConnectionDot({ status, demo }: Props) {
  const display = demo ? "Demo" : label[status];
  const cls     = demo ? "bg-blue-DEFAULT" : dot[status];
  return (
    <div className="flex items-center gap-2">
      <span className={clsx("h-2 w-2 rounded-full", cls)} />
      <span className="text-xs font-medium tracking-wide text-muted">
        {display}
      </span>
    </div>
  );
}
