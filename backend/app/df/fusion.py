"""Per-track geolocation fusion over time.

A constant-position Kalman filter with a random-walk process model: process
noise ``Q`` lets a fix track a moving emitter with bounded lag while still
shrinking the ellipse for a stationary one.
"""

from __future__ import annotations

import numpy as np


class GeoFusion:
    def __init__(self, process_km_per_update: float = 0.6) -> None:
        self._p: np.ndarray | None = None
        self._P: np.ndarray | None = None
        self._q = float(process_km_per_update) ** 2
        self.history: list[dict] = []

    def update(self, z: np.ndarray, R: np.ndarray, time_slot: int) -> tuple[np.ndarray, np.ndarray]:
        z = np.asarray(z, dtype=float)
        R = np.asarray(R, dtype=float)
        if self._p is None or not np.all(np.isfinite(self._P)):
            self._p = z.copy()
            self._P = R.copy()
        else:
            P_pred = self._P + self._q * np.eye(2)
            K = P_pred @ np.linalg.inv(P_pred + R)
            self._p = self._p + K @ (z - self._p)
            self._P = (np.eye(2) - K) @ P_pred
        self.history.append(
            {
                "time_slot": int(time_slot),
                "x_km": round(float(self._p[0]), 4),
                "y_km": round(float(self._p[1]), 4),
            }
        )
        del self.history[:-400]
        return self._p.copy(), self._P.copy()

    @property
    def state(self):
        return (None, None) if self._p is None else (self._p.copy(), self._P.copy())
