"""Manage up to 3 KiteTicker WebSocket connections (Kite hard limit)."""
from __future__ import annotations

import logging

from kiteconnect import KiteTicker

import config
from feed.tick_queue import TickQueue

log = logging.getLogger("ticker")


class TickerManager:
    def __init__(self, api_key: str, access_token: str,
                 tokens: list[int], tick_queue: TickQueue):
        if len(tokens) > config.WS_MAX_PER_CONNECTION * config.WS_MAX_CONNECTIONS:
            raise ValueError(
                f"{len(tokens)} tokens exceed Kite capacity "
                f"({config.WS_MAX_CONNECTIONS} x {config.WS_MAX_PER_CONNECTION})"
            )
        self._api_key = api_key
        self._access_token = access_token
        self._chunks = [
            tokens[i:i + config.WS_MAX_PER_CONNECTION]
            for i in range(0, len(tokens), config.WS_MAX_PER_CONNECTION)
        ]
        self._queue = tick_queue
        self._tickers: list[KiteTicker] = []
        self._build_tickers()

    def _build_tickers(self) -> None:
        self._tickers = []
        for idx, chunk in enumerate(self._chunks):
            ticker = KiteTicker(self._api_key, self._access_token)
            self._wire(ticker, chunk, idx)
            self._tickers.append(ticker)

    def _wire(self, ticker: KiteTicker, chunk: list[int], idx: int) -> None:
        q = self._queue

        def on_ticks(ws, ticks):
            q.put_ticks(ticks)

        def on_connect(ws, response):
            log.info("WS-%d connected, subscribing %d tokens (FULL mode)",
                     idx, len(chunk))
            ws.subscribe(chunk)
            ws.set_mode(ws.MODE_FULL, chunk)

        def on_close(ws, code, reason):
            log.warning("WS-%d closed: %s %s", idx, code, reason)

        def on_error(ws, code, reason):
            log.error("WS-%d error: %s %s", idx, code, reason)

        def on_reconnect(ws, attempts):
            log.warning("WS-%d reconnecting (attempt %d)", idx, attempts)

        def on_noreconnect(ws):
            log.error("WS-%d gave up reconnecting - feed degraded!", idx)

        ticker.on_ticks = on_ticks
        ticker.on_connect = on_connect
        ticker.on_close = on_close
        ticker.on_error = on_error
        ticker.on_reconnect = on_reconnect
        ticker.on_noreconnect = on_noreconnect

    def start(self) -> None:
        log.info("Starting %d WebSocket connection(s) for %d tokens",
                 len(self._tickers), sum(len(c) for c in self._chunks))
        for ticker in self._tickers:
            # returns immediately; callbacks fire on those threads.
            ticker.connect(threaded=True)

    def stop(self) -> None:
        for idx, ticker in enumerate(self._tickers):
            try:
                ticker.stop_retry()
            except Exception:
                pass
            try:
                ticker.close()
            except Exception as exc:
                log.warning("WS-%d close error: %s", idx, exc)
        log.info("All WebSocket connections closed.")

    def force_reconnect(self, access_token: str | None = None) -> None:
        """Hard-recycle every connection: close + recreate + reconnect."""
        if access_token:
            self._access_token = access_token
        log.critical("FORCE RECONNECT: recycling %d WebSocket connection(s)",
                     len(self._tickers))
        self.stop()
        self._build_tickers()
        self.start()

    def is_alive(self) -> bool:
        return any(t.is_connected() for t in self._tickers)
