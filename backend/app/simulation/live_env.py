"""Live receive-only environment.

Presents the same surface :class:`Simulation` / :class:`Receiver` /
:class:`MetricsTracker` expect from :class:`RFEnvironment`, but each time slot
is filled from the newest DSP :class:`BandObservation` set instead of a
pre-generated ground-truth matrix.

There is no real ground truth on live RF, so ``occupancy`` here means "the DSP
saw energy above threshold" and ``threat`` is zero. Ground-truth-derived metrics
(P(detection), interception ratio, ...) therefore carry *proxy* semantics in
live mode — see the manager's ``metrics_applicability`` flag and Step 8.
"""

from __future__ import annotations

import numpy as np

from ..models.core import Band, HardwareConfig

_LIVE_SLOT_CAP = 20_000


class LiveRFEnvironment:
    replayed = True  # keeps existing "not a fresh sim" UI affordances working
    live = True

    def __init__(self, config: HardwareConfig, hardware_manager) -> None:
        self._hw = hardware_manager
        self.config = config
        self.num_bands = int(config.num_bands)
        self.num_time_slots = _LIVE_SLOT_CAP
        self.noise_floor_db = -100.0

        span_mhz = max(config.stop_freq_hz - config.start_freq_hz, 1.0) / 1e6
        width_mhz = span_mhz / self.num_bands
        base_mhz = config.start_freq_hz / 1e6
        self.bands: list[Band] = [
            Band(
                index=i,
                center_mhz=round(base_mhz + (i + 0.5) * width_mhz, 4),
                width_mhz=round(width_mhz, 6),
            )
            for i in range(self.num_bands)
        ]
        self.emitters: list = []
        self.events: list = []

        shape = (self.num_time_slots, self.num_bands)
        self.occupancy = np.zeros(shape, dtype=bool)
        self.snr_db = np.zeros(shape, dtype=np.float32)
        self.power_db = np.full(shape, self.noise_floor_db, dtype=np.float32)
        self.threat = np.zeros(shape, dtype=np.float32)
        self.emitter_id_matrix = np.full(shape, -1, dtype=np.int32)
        # Live has no simulated EW effects; observed == the DSP-filled matrices.
        self.occupancy_observed = self.occupancy
        self.snr_observed = self.snr_db
        self.power_observed = self.power_db
        self.is_synthetic_effect = None
        self.effect_labels: list[dict] = []
        self._filled_t = -1

    # ------------------------------------------------------------------ #
    def ingest_step(self, t: int) -> None:
        """Called by :meth:`Simulation.step` before the env is read at slot ``t``."""
        if t >= self.num_time_slots:
            return
        obs = self._hw.latest_observations()
        if not obs:
            # No frame yet — carry the previous row forward (or leave noise floor).
            if self._filled_t >= 0 and t > 0:
                self.occupancy[t] = self.occupancy[self._filled_t]
                self.snr_db[t] = self.snr_db[self._filled_t]
                self.power_db[t] = self.power_db[self._filled_t]
            self._filled_t = t
            return

        floor = float(obs[0].noise_floor_dbm) if obs else self.noise_floor_db
        self.noise_floor_db = floor
        for o in obs:
            b = o.band
            if 0 <= b < self.num_bands:
                self.occupancy[t, b] = o.active
                self.snr_db[t, b] = o.snr_db
                self.power_db[t, b] = o.power_dbm
        self._filled_t = t

    # ------------------------------------------------------------------ #
    # RFEnvironment-compatible queries
    # ------------------------------------------------------------------ #
    def is_active(self, t: int, band: int) -> bool:
        return bool(self.occupancy[min(t, self.num_time_slots - 1), band])

    def active_bands(self, t: int) -> list[int]:
        return np.nonzero(self.occupancy[min(t, self.num_time_slots - 1)])[0].tolist()

    def snr_at(self, t: int, band: int) -> float:
        return float(self.snr_db[min(t, self.num_time_slots - 1), band])

    def power_at(self, t: int, band: int) -> float:
        return float(self.power_db[min(t, self.num_time_slots - 1), band])

    def threat_at(self, t: int, band: int) -> float:
        return 0.0

    def events_started_by(self, t: int) -> list:
        return []

    def band_threat_prior(self) -> np.ndarray:
        return np.zeros(self.num_bands, dtype=np.float32)

    def occupancy_percentage(self) -> float:
        hi = max(self._filled_t + 1, 1)
        return float(self.occupancy[:hi].mean())
