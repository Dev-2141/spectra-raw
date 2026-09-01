"""Process-wide platform mode state."""

from __future__ import annotations

import threading
from datetime import datetime, timezone

MODES: tuple[str, ...] = ("simulation", "live_es")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ModeManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._mode = "simulation"
        self._degraded = False
        self._since = _utc_now()

    @property
    def mode(self) -> str:
        return self._mode

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "mode": self._mode,
                "degraded": self._degraded,
                "since": self._since,
                "hardware_mode": "receive_only",
                "transmit_capability": False,
            }

    def set_mode(self, mode: str, *, hardware_configured: bool = False) -> dict:
        if mode not in MODES:
            raise ValueError(f"unknown mode: {mode!r} (expected one of {MODES})")
        with self._lock:
            self._mode = mode
            self._degraded = mode == "live_es" and not hardware_configured
            self._since = _utc_now()
        return self.snapshot()


# --------------------------------------------------------------------------- #
_manager: ModeManager | None = None


def get_mode_manager() -> ModeManager:
    global _manager
    if _manager is None:
        _manager = ModeManager()
    return _manager


def _reset_for_tests() -> None:
    global _manager
    _manager = None
