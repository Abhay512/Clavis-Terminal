"use client";
import { useEffect, useState } from "react";

function pad(n: number) { return String(n).padStart(2, "0"); }

function timeStr() {
  const d = new Date();
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function marketPhase(): { label: string; color: string } {
  const d = new Date();
  const t = d.getHours() * 60 + d.getMinutes();
  if (t < 9 * 60 + 15)  return { label: "Pre-market", color: "text-amber-DEFAULT" };
  if (t < 15 * 60 + 30) return { label: "Market Open", color: "text-green-DEFAULT" };
  return                        { label: "Market Closed", color: "text-muted" };
}

export default function MarketClock() {
  const [time, setTime] = useState(timeStr);
  const [phase, setPhase] = useState(marketPhase);

  useEffect(() => {
    const id = setInterval(() => {
      setTime(timeStr());
      setPhase(marketPhase());
    }, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="flex items-center gap-3">
      <span className={`text-xs font-medium ${phase.color}`}>{phase.label}</span>
      <span className="font-mono text-sm text-text tabular-nums">{time}</span>
    </div>
  );
}
