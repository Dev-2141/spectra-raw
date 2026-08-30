"""Tabular Q-learning scheduler.

State  = (current-band bucket, recent-hit bucket, time-since-last-visit bucket,
          threat bucket, time modulo periodic window bucket)
Action = index of the next band to scan
Q      = dict[state] -> np.ndarray(num_bands)

The temporal-difference update for the previous (s, a) is applied at the top of
the next ``decide`` call, when the successor state s' is known. Call
``end_episode`` between training episodes to flush the final transition and
clear the trajectory while keeping the learned Q-table.
"""

from __future__ import annotations

from collections import deque

import numpy as np

from ..models.core import ScanDecision
from .base import BaseScheduler

StateKey = tuple[int, int, int, int, int]


class QLearningScheduler(BaseScheduler):
    name = "q_learning"

    def __init__(self, num_bands: int, rng, params: dict | None = None):
        super().__init__(num_bands, rng, params)
        p = self.params
        self.alpha = float(p.get("alpha", 0.2))
        self.gamma = float(p.get("gamma", 0.9))
        self.epsilon = float(p.get("epsilon", 0.2))
        self.epsilon_min = float(p.get("epsilon_min", 0.02))
        self.epsilon_decay = float(p.get("epsilon_decay", 0.9995))
        self.periodic_window = int(p.get("periodic_window", 20))
        self.band_buckets = int(p.get("band_buckets", 8))
        self.optimistic_init = float(p.get("optimistic_init", 0.0))

        self.q: dict[StateKey, np.ndarray] = {}
        self._recent_hits: deque[int] = deque(maxlen=8)
        self._prev_state: StateKey | None = None
        self._prev_action: int | None = None
        self._pending_reward: float | None = None
        self.updates = 0

    # ------------------------------------------------------------------ #
    def reset(self) -> None:
        self.q.clear()
        self._recent_hits.clear()
        self._prev_state = None
        self._prev_action = None
        self._pending_reward = None
        self.updates = 0
        self.epsilon = float(self.params.get("epsilon", 0.2))

    def _row(self, state: StateKey) -> np.ndarray:
        row = self.q.get(state)
        if row is None:
            row = np.full(self.num_bands, self.optimistic_init, dtype=np.float64)
            self.q[state] = row
        return row

    def _encode(self, context) -> StateKey:
        B = self.num_bands
        cb = context.current_band
        cb_bucket = int(cb * self.band_buckets // max(1, B))

        hits = sum(self._recent_hits)
        hit_bucket = 0 if hits == 0 else 1 if hits <= 2 else 2 if hits <= 4 else 3

        lv = int(context.last_visit_slot[cb])
        since = 10_000 if lv < 0 else context.time_slot - lv
        tslv_bucket = 0 if since <= 2 else 1 if since <= 8 else 2 if since <= 32 else 3

        threat_bucket = int(min(3, context.band_threat_prior[cb] * 4))
        tmod = (context.time_slot % self.periodic_window) * 4 // self.periodic_window
        return (cb_bucket, hit_bucket, tslv_bucket, threat_bucket, int(tmod))

    # ------------------------------------------------------------------ #
    def decide(self, context) -> ScanDecision:
        state = self._encode(context)

        # TD update for the previous transition, now that s' is known.
        if (
            self._prev_state is not None
            and self._prev_action is not None
            and self._pending_reward is not None
        ):
            prev = self._row(self._prev_state)
            best_next = float(np.max(self._row(state)))
            target = self._pending_reward + self.gamma * best_next
            prev[self._prev_action] += self.alpha * (target - prev[self._prev_action])
            self.updates += 1
            self._pending_reward = None

        row = self._row(state)
        explore = self.rng.random() < self.epsilon
        if explore:
            action = int(self.rng.integers(0, self.num_bands))
            reasons = [
                f"epsilon-greedy exploration (epsilon={self.epsilon:.3f})",
                f"state {state}",
                f"{len(self.q)} states seen, {self.updates} TD updates",
            ]
            conf = self.epsilon
        else:
            action = int(np.argmax(row))
            reasons = [
                f"greedy argmax Q (Q={row[action]:.3f})",
                f"state {state}",
                f"{self.updates} TD updates so far",
            ]
            conf = _softmax_confidence(row, action)

        self._prev_state = state
        self._prev_action = action
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

        pa = float(context.predicted_activity[action])
        visited = context.visit_counts[action] >= 2
        predicted_active = True if pa >= 0.5 else (False if (visited and pa <= 0.1) else None)

        order = np.argsort(row)[::-1]
        alts = [int(b) for b in order[:4] if int(b) != action][:3]
        return self._decision(
            context=context,
            band=action,
            confidence=conf,
            predicted_active=predicted_active,
            reasons=reasons,
            alternatives=alts,
            explanation=(
                f"Q-learning {'explores' if explore else 'exploits'} band {action} "
                f"from state {state}; Q={row[action]:.3f}, epsilon={self.epsilon:.3f}."
            ),
        )

    def update(self, feedback) -> None:
        self._pending_reward = feedback.reward
        self._recent_hits.append(
            1 if (feedback.detected and feedback.true_active) else 0
        )

    def end_episode(self) -> None:
        """Flush the terminal transition (no bootstrap) and clear the trajectory."""
        if (
            self._prev_state is not None
            and self._prev_action is not None
            and self._pending_reward is not None
        ):
            prev = self._row(self._prev_state)
            prev[self._prev_action] += self.alpha * (
                self._pending_reward - prev[self._prev_action]
            )
            self.updates += 1
        self._prev_state = None
        self._prev_action = None
        self._pending_reward = None
        self._recent_hits.clear()


def _softmax_confidence(row: np.ndarray, idx: int) -> float:
    z = row - row.max()
    p = np.exp(z)
    p /= p.sum()
    return float(p[idx])
