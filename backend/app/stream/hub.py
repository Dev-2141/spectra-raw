"""In-process pub/sub hub feeding the ``/ws`` channel.

Each subscriber gets a bounded queue. Under backpressure, ``state`` / ``frame``
/ ``metric`` events drop oldest-first; ``alert`` events are never dropped (the
queue is allowed to exceed the soft cap for them). Every event carries a
monotonic per-type sequence number.
"""

from __future__ import annotations

import asyncio
import threading

_SOFT_CAP = 256
_NEVER_DROP = {"alert"}


class _Subscriber:
    def __init__(self) -> None:
        self.queue: asyncio.Queue = asyncio.Queue()
        self.dropped = 0


class StreamHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: set[_Subscriber] = set()
        self._seq: dict[str, int] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # ------------------------------------------------------------------ #
    def subscribe(self) -> _Subscriber:
        sub = _Subscriber()
        with self._lock:
            self._subs.add(sub)
        return sub

    def unsubscribe(self, sub: _Subscriber) -> None:
        with self._lock:
            self._subs.discard(sub)

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subs)

    # ------------------------------------------------------------------ #
    def publish(self, event_type: str, payload: dict) -> dict:
        """Fan out an event. Safe to call from any thread."""
        with self._lock:
            self._seq[event_type] = self._seq.get(event_type, 0) + 1
            seq = self._seq[event_type]
            subs = list(self._subs)
        event = {"type": event_type, "seq": seq, "payload": payload}

        for sub in subs:
            if (
                event_type not in _NEVER_DROP
                and sub.queue.qsize() >= _SOFT_CAP
            ):
                try:
                    sub.queue.get_nowait()
                    sub.dropped += 1
                except asyncio.QueueEmpty:
                    pass
            self._enqueue(sub, event)
        return event

    def _enqueue(self, sub: _Subscriber, event: dict) -> None:
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(sub.queue.put_nowait, event)
        else:  # same-thread (tests / startup)
            try:
                sub.queue.put_nowait(event)
            except Exception:
                pass


_hub: StreamHub | None = None


def get_stream_hub() -> StreamHub:
    global _hub
    if _hub is None:
        _hub = StreamHub()
    return _hub


def _reset_for_tests() -> None:
    global _hub
    _hub = None
