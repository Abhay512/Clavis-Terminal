"use client";
import { useState } from "react";
import { motion } from "framer-motion";
import { ChevronDown, WifiOff } from "lucide-react";
import BigPlayerRadar from "@/components/BigPlayerRadar";
import Header from "@/components/Header";
import OIBuildupBoard from "@/components/OIBuildupBoard";
import OneWayMovers from "@/components/OneWayMovers";
import PositionRadar from "@/components/PositionRadar";
import RankingTable from "@/components/RankingTable";
import SectorLeaders from "@/components/SectorLeaders";
import SignalFeed from "@/components/SignalFeed";
import StatusBar from "@/components/StatusBar";
import { useLiveData } from "@/hooks/useLiveData";

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO === "true";

const FADE = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: 0.15 } },
};

const STAGGER = {
  show: { transition: { staggerChildren: 0.03 } },
};

export default function DashboardPage() {
  const { topBuy, topSell, position, oneway, onewayExits, radar, oimult, sector, signals, status, rankingTs, wsStatus } = useLiveData();
  const [showRef, setShowRef] = useState(false);
  const disconnected = !DEMO_MODE && wsStatus !== "connected";

  return (
    <div className="flex min-h-screen flex-col">
      <Header status={status} wsStatus={wsStatus} demo={DEMO_MODE} />

      {disconnected && (
        <div className="relative flex items-center justify-center gap-2 border-b border-amber-DEFAULT/30 bg-amber-DEFAULT/10 px-4 py-2 text-2xs font-medium text-amber-DEFAULT">
          <WifiOff className="h-3.5 w-3.5" />
          {wsStatus === "connecting" ? "Connecting to the screener backend..." : "Backend disconnected - reconnecting. Start it with: python main.py --now --api"}
        </div>
      )}

      <motion.main
        className="relative flex flex-1 flex-col gap-3 p-4"
        variants={STAGGER}
        initial="hidden"
        animate="show"
      >
        <motion.div variants={FADE} className="shrink-0">
          <OneWayMovers movers={oneway} exits={onewayExits} />
        </motion.div>

        <motion.div variants={FADE} className="shrink-0">
          <SectorLeaders rows={sector} />
        </motion.div>

        <motion.div variants={FADE} className="flex shrink-0 flex-col items-stretch gap-3 lg:flex-row">
          <div className="min-w-0 flex-1">
            <BigPlayerRadar signals={radar} />
          </div>
          <div className="min-w-0 flex-1">
            <PositionRadar builds={position} />
          </div>
        </motion.div>

        <motion.div variants={FADE} className="shrink-0">
          <OIBuildupBoard rows={oimult} />
        </motion.div>

        <motion.div variants={FADE} className="shrink-0">
          <button
            type="button"
            onClick={() => setShowRef(v => !v)}
            className="flex w-full items-center justify-between rounded-xl border border-border bg-card px-4 py-2.5 text-left text-xs font-semibold text-muted transition-colors hover:bg-cardHover"
          >
            <span>Reference - raw OI build-up ranking &amp; live spike feed</span>
            <ChevronDown className={`h-4 w-4 transition-transform ${showRef ? "rotate-180" : ""}`} />
          </button>
          {showRef && (
            <div className="mt-3 flex items-start gap-3">
              <div className="min-w-0 flex-1">
                <RankingTable side="buy" rows={topBuy} rankingTs={rankingTs} />
              </div>
              <div className="min-w-0 flex-1">
                <RankingTable side="sell" rows={topSell} rankingTs={rankingTs} />
              </div>
              <div className="flex w-80 shrink-0 flex-col xl:w-96">
                <SignalFeed signals={signals} />
              </div>
            </div>
          )}
        </motion.div>
      </motion.main>

      <StatusBar status={status} rankingTs={rankingTs} />
    </div>
  );
}
