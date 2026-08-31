"""Process-wide tasking state.

Protected bands (Step 1), plus watch lists and alert rules (Step 4). Watch
lists and rules are held in memory like protected bands; durable storage is a
Step 7 concern.
"""

from __future__ import annotations

import threading
import uuid

import numpy as np

from ..config import get_settings
from ..models.core import AlertRule, WatchList

_DEFAULT_RULES = [
    AlertRule(id="rule_new_emitter", kind="new_emitter", severity="info"),
    AlertRule(id="rule_priority_hit", kind="priority_hit", severity="critical", threshold=0.7),
    AlertRule(id="rule_hop_detected", kind="hop_detected", severity="warn"),
    AlertRule(id="rule_anomaly", kind="anomaly", severity="warn"),
    AlertRule(id="rule_library_match", kind="library_match", severity="warn", threshold=0.6),
]


class TaskingState:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._protected: set[int] = {
            int(b) for b in get_settings().protected_bands if int(b) >= 0
        }
        self._watch_lists: list[WatchList] = []
        self._alert_rules: list[AlertRule] = [r.model_copy(deep=True) for r in _DEFAULT_RULES]

    # --- protected bands ---------------------------------------------- #
    @property
    def protected_bands(self) -> set[int]:
        with self._lock:
            return set(self._protected)

    def set_protected_bands(self, bands: list[int]) -> list[int]:
        with self._lock:
            self._protected = {int(b) for b in bands if int(b) >= 0}
            return sorted(self._protected)

    # --- watch lists ------------------------------------------------- #
    @property
    def watch_lists(self) -> list[WatchList]:
        with self._lock:
            return [w.model_copy(deep=True) for w in self._watch_lists]

    def set_watch_lists(self, items: list[WatchList]) -> list[WatchList]:
        with self._lock:
            out: list[WatchList] = []
            for w in items:
                w = w.model_copy(deep=True)
                if not w.id:
                    w.id = f"wl_{uuid.uuid4().hex[:8]}"
                out.append(w)
            self._watch_lists = out
            return [w.model_copy(deep=True) for w in out]

    def band_weights(self, num_bands: int) -> np.ndarray:
        w = np.ones(num_bands, dtype=np.float64)
        with self._lock:
            for wl in self._watch_lists:
                if not wl.enabled:
                    continue
                lo = max(0, min(num_bands - 1, wl.band_lo))
                hi = max(lo, min(num_bands - 1, wl.band_hi or wl.band_lo))
                w[lo : hi + 1] = np.maximum(w[lo : hi + 1], float(wl.weight))
        return w

    # --- alert rules ----------------------------------------------- #
    @property
    def alert_rules(self) -> list[AlertRule]:
        with self._lock:
            return [r.model_copy(deep=True) for r in self._alert_rules]

    def set_alert_rules(self, items: list[AlertRule]) -> list[AlertRule]:
        with self._lock:
            out: list[AlertRule] = []
            for r in items:
                r = r.model_copy(deep=True)
                if not r.id:
                    r.id = f"rule_{uuid.uuid4().hex[:8]}"
                out.append(r)
            self._alert_rules = out
            return [r.model_copy(deep=True) for r in out]


_state: TaskingState | None = None


def get_tasking_state() -> TaskingState:
    global _state
    if _state is None:
        _state = TaskingState()
    return _state


def _reset_for_tests() -> None:
    global _state
    _state = None
