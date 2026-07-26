"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import type { WsMessage } from "@/lib/types";

type Status = "connecting" | "connected" | "reconnecting" | "offline";

interface UseWebSocketReturn {
  status: Status;
  lastMessage: WsMessage | null;
}

const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 15000]; // ms, capped
const STALE_MS = 75_000;
const STALE_CHECK_MS = 15_000;

export function useWebSocket(
  url: string,
  onMessage?: (msg: WsMessage) => void
): UseWebSocketReturn {
  const [status, setStatus] = useState<Status>("connecting");
  const [lastMessage, setLastMessage] = useState<WsMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const attemptsRef = useRef(0);
  const unmountedRef = useRef(false);
  const lastMsgAtRef = useRef(0);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const connect = useCallback(() => {
    if (unmountedRef.current || !url) return;
    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (unmountedRef.current) { ws.close(); return; }
        attemptsRef.current = 0;
        lastMsgAtRef.current = Date.now();
        setStatus("connected");
      };

      ws.onmessage = (ev) => {
        lastMsgAtRef.current = Date.now();
        try {
          const msg = JSON.parse(ev.data) as WsMessage;
          onMessageRef.current?.(msg);
          setLastMessage(msg);
        } catch { /* ignore malformed */ }
      };

      ws.onclose = () => {
        if (unmountedRef.current) return;
        const delay =
          RECONNECT_DELAYS[
            Math.min(attemptsRef.current, RECONNECT_DELAYS.length - 1)
          ];
        attemptsRef.current++;
        setStatus(attemptsRef.current === 1 ? "reconnecting" : "offline");
        setTimeout(connect, delay);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      setStatus("offline");
    }
  }, [url]);

  useEffect(() => {
    unmountedRef.current = false;
    if (!url) { setStatus("offline"); return; }
    connect();
    const watchdog = setInterval(() => {
      const ws = wsRef.current;
      if (
        ws &&
        ws.readyState === WebSocket.OPEN &&
        Date.now() - lastMsgAtRef.current > STALE_MS
      ) {
        ws.close();
      }
    }, STALE_CHECK_MS);
    return () => {
      unmountedRef.current = true;
      clearInterval(watchdog);
      wsRef.current?.close();
    };
  }, [connect, url]);

  return { status, lastMessage };
}
