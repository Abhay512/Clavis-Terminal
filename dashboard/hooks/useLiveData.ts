"use client";
import { useCallback, useEffect, useMemo, useReducer } from "react";
import { useWebSocket } from "./useWebSocket";
import type { Signal, StockRank, ScreenerStatus, PositionBuild, OneWayMover, BigPlayerSignal, OIMultipleRow, SectorLeader, WsMessage } from "@/lib/types";
import { MOCK_RANKINGS, MOCK_STATUS, MOCK_POSITION, MOCK_ONEWAY, MOCK_RADAR, MOCK_OIMULT, MOCK_SECTOR, makeMockSignal } from "@/lib/mock";

const WS_URL = process.env.NEXT_PUBLIC_API_WS ?? "ws://localhost:8000/ws/live";
const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO === "true";
const MAX_SIGNALS = 120;
const TOP_ROWS = 30;

interface State {
  rankings: StockRank[];
  position: PositionBuild[];
  oneway: OneWayMover[];
  onewayExits: OneWayMover[];  // today's stopped/closed rides (newest first)
  radar: BigPlayerSignal[];
  oimult: OIMultipleRow[];
  sector: SectorLeader[];
  signals: Signal[];   // newest first
  status: ScreenerStatus;
  rankingTs: string;
}

type Action =
  | { type: "SIGNAL";   payload: Signal }
  | { type: "RANKING";  payload: StockRank[] }
  | { type: "POSITION"; payload: PositionBuild[] }
  | { type: "ONEWAY";   payload: OneWayMover[] }
  | { type: "RADAR";    payload: BigPlayerSignal[] }
  | { type: "OIMULT";   payload: OIMultipleRow[] }
  | { type: "SECTOR";   payload: SectorLeader[] }
  | { type: "HISTORY";  payload: Signal[] }
  | { type: "STATUS";   payload: ScreenerStatus };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "SIGNAL":
      return {
        ...state,
        signals: [action.payload, ...state.signals].slice(0, MAX_SIGNALS),
        status: {
          ...state.status,
          signals_today: (state.status.signals_today ?? 0) + 1,
        },
      };
    case "RANKING":
      return {
        ...state,
        rankings: action.payload,
        rankingTs: action.payload[0]?.ts ?? state.rankingTs,
      };
    case "POSITION":
      return { ...state, position: action.payload };
    case "ONEWAY": {
      const exits = action.payload.filter(m => m.status === "EXIT");
      let onewayExits = state.onewayExits;
      if (exits.length > 0) {
        const seen = new Set(exits.map(m => `${m.underlying}|${m.entry_ts}`));
        onewayExits = [
          ...exits,
          ...state.onewayExits.filter(m => !seen.has(`${m.underlying}|${m.entry_ts}`)),
        ].slice(0, 60);
      }
      return { ...state, oneway: action.payload.filter(m => m.status !== "EXIT"), onewayExits };
    }
    case "RADAR":
      return { ...state, radar: action.payload };
    case "OIMULT":
      return { ...state, oimult: action.payload };
    case "SECTOR":
      return { ...state, sector: action.payload };
    case "HISTORY":
      return {
        ...state,
        signals: [...action.payload].reverse().slice(0, MAX_SIGNALS),
      };
    case "STATUS":
      return { ...state, status: action.payload };
    default:
      return state;
  }
}

const INIT: State = {
  rankings: [],
  position: [],
  oneway: [],
  onewayExits: [],
  radar: [],
  oimult: [],
  sector: [],
  signals: [],
  status: { market_open: false, instruments: 0, signals_today: 0 },
  rankingTs: "",
};

export function useLiveData() {
  const [state, dispatch] = useReducer(reducer, INIT);

  const handleMessage = useCallback((msg: WsMessage) => {
    if (msg.type === "signal")   dispatch({ type: "SIGNAL",   payload: msg.data });
    if (msg.type === "ranking")  dispatch({ type: "RANKING",  payload: msg.data });
    if (msg.type === "position") dispatch({ type: "POSITION", payload: msg.data });
    if (msg.type === "oneway")   dispatch({ type: "ONEWAY",   payload: msg.data });
    if (msg.type === "radar")    dispatch({ type: "RADAR",    payload: msg.data });
    if (msg.type === "oimult")   dispatch({ type: "OIMULT",   payload: msg.data });
    if (msg.type === "sector")   dispatch({ type: "SECTOR",   payload: msg.data });
    if (msg.type === "history")  dispatch({ type: "HISTORY",  payload: msg.data });
    if (msg.type === "status")   dispatch({ type: "STATUS",   payload: msg.data });
  }, []);

  const { status: wsStatus } = useWebSocket(
    DEMO_MODE ? "" : WS_URL, handleMessage
  );

  useEffect(() => {
    if (!DEMO_MODE) return;
    dispatch({ type: "STATUS",   payload: MOCK_STATUS });
    dispatch({ type: "RANKING",  payload: MOCK_RANKINGS });
    dispatch({ type: "POSITION", payload: MOCK_POSITION });
    dispatch({ type: "ONEWAY",   payload: MOCK_ONEWAY });
    dispatch({ type: "RADAR",    payload: MOCK_RADAR });
    dispatch({ type: "OIMULT",   payload: MOCK_OIMULT });
    dispatch({ type: "SECTOR",   payload: MOCK_SECTOR });
    if (state.signals.length === 0) {
      for (let i = 0; i < 8; i++) {
        dispatch({ type: "SIGNAL", payload: makeMockSignal() });
      }
    }
    const interval = setInterval(() => {
      dispatch({ type: "SIGNAL", payload: makeMockSignal() });
    }, 4000);
    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const topBuy = useMemo(
    () => [...state.rankings]
      .sort((a, b) => b.buy_notional_cr - a.buy_notional_cr)
      .filter(r => r.buy_notional_cr > 0)
      .slice(0, TOP_ROWS),
    [state.rankings]
  );
  const topSell = useMemo(
    () => [...state.rankings]
      .sort((a, b) => b.sell_notional_cr - a.sell_notional_cr)
      .filter(r => r.sell_notional_cr > 0)
      .slice(0, TOP_ROWS),
    [state.rankings]
  );

  return { ...state, topBuy, topSell, wsStatus };
}
