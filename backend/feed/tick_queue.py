"""Thread-safe bridge between KiteTicker callback threads and the engine."""
from __future__ import annotations

import queue
from typing import Any


class TickQueue:
    def __init__(self, maxsize: int = 100_000):
        self._q: queue.Queue = queue.Queue(maxsize=maxsize)
        self.dropped = 0

    def put_ticks(self, ticks: list[dict[str, Any]]) -> None:
        """Called from ticker threads. Never blocks the feed."""
        try:
            self._q.put_nowait(ticks)
        except queue.Full:
            self.dropped += 1

    def drain(self, timeout: float = 0.2) -> list[dict[str, Any]]:
        """Called from the consumer thread. Returns a flat list of ticks,
        waiting at most `timeout` for the first batch."""
        ticks: list[dict[str, Any]] = []
        try:
            ticks.extend(self._q.get(timeout=timeout))
        except queue.Empty:
            return ticks
        # Drain whatever else is already queued without waiting.
        while True:
            try:
                ticks.extend(self._q.get_nowait())
            except queue.Empty:
                break
        return ticks

    def qsize(self) -> int:
        return self._q.qsize()
