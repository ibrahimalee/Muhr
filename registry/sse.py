"""Server-Sent Events broadcaster.

- Bounded history (new clients get the last ``HISTORY`` events, not everything ever).
- One ``asyncio.Queue`` per subscriber, tracked by identity, so a disconnect can
  never remove a different client's queue.
- ``publish`` is safe to call from FastAPI's threadpool (sync endpoints) or from
  the event loop: delivery is scheduled with ``call_soon_threadsafe`` on the loop
  that owns each subscriber.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import deque
from typing import AsyncIterator

from shared import schemas

logger = logging.getLogger(__name__)

HISTORY = 500
QUEUE_MAX = 1000
HEARTBEAT_SECONDS = 15.0


class Broadcaster:
    def __init__(self, history: int = HISTORY) -> None:
        self._lock = threading.Lock()
        self.history: deque[str] = deque(maxlen=history)
        self._subs: dict[int, tuple[asyncio.Queue[str], asyncio.AbstractEventLoop]] = {}

    @staticmethod
    def encode(event: schemas.FeedEvent) -> str:
        return json.dumps(event.model_dump(mode="json"))

    def publish(self, event: schemas.FeedEvent) -> None:
        data = self.encode(event)
        with self._lock:
            self.history.append(data)
            subs = list(self._subs.values())
        for queue, loop in subs:
            try:
                loop.call_soon_threadsafe(self._offer, queue, data)
            except RuntimeError:  # loop already closed
                pass
        logger.info("SSE event: %s - %s", event.type, event.detail)

    def extend_history(self, events: list[schemas.FeedEvent]) -> None:
        with self._lock:
            for e in events:
                self.history.append(self.encode(e))

    @staticmethod
    def _offer(queue: asyncio.Queue[str], data: str) -> None:
        if queue.full():  # slow client: drop its oldest event rather than grow forever
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        queue.put_nowait(data)

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subs)

    async def stream(self) -> AsyncIterator[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=QUEUE_MAX)
        key = id(queue)
        with self._lock:
            backlog = list(self.history)
            self._subs[key] = (queue, asyncio.get_running_loop())
        try:
            yield ": connected\n\n"
            for data in backlog:
                yield f"data: {data}\n\n"
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                yield f"data: {data}\n\n"
        finally:
            with self._lock:
                self._subs.pop(key, None)


broadcaster = Broadcaster()
