"use client";
interface Props {
  value: number;
  max: number;
  color: "green" | "red";
}

export default function RankBar({ value, max, color }: Props) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  const bg = color === "green" ? "bg-green-DEFAULT/20" : "bg-red-DEFAULT/20";
  const fill = color === "green" ? "bg-green-DEFAULT" : "bg-red-DEFAULT";
  return (
    <div className={`relative h-1 w-full overflow-hidden rounded-full ${bg}`}>
      <div
        className={`absolute left-0 top-0 h-full rounded-full transition-all duration-300 ease-snap ${fill}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
