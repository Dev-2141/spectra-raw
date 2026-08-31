"""Sweep -> per-band observations.

Everything here is deterministic given its inputs and unit-tested against
synthetic frames (``test_ext_step2.py``).
"""

from __future__ import annotations

import numpy as np

from ..models.core import BandObservation, SweepFrame


def estimate_noise_floor(power_dbm: np.ndarray, percentile: float = 25.0) -> float:
    """Robust noise-floor estimate: a low percentile of the power bins."""
    finite = power_dbm[np.isfinite(power_dbm)]
    if finite.size == 0:
        return -120.0
    return float(np.percentile(finite, percentile))


def bins_to_bands(
    power_dbm: np.ndarray,
    f_start_hz: float,
    f_stop_hz: float,
    bin_hz: float,
    num_bands: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Aggregate FFT bins onto ``num_bands`` equal-width bands.

    Returns ``(band_peak_dbm, band_mean_dbm)`` — peak-hold is used for
    occupancy sensitivity, the mean feeds the local noise estimate.
    """
    n_bins = power_dbm.shape[0]
    if n_bins == 0 or num_bands <= 0:
        return (
            np.full(max(num_bands, 0), -120.0, dtype=np.float64),
            np.full(max(num_bands, 0), -120.0, dtype=np.float64),
        )
    span = max(f_stop_hz - f_start_hz, bin_hz)
    bin_centers = f_start_hz + (np.arange(n_bins) + 0.5) * bin_hz
    idx = np.floor((bin_centers - f_start_hz) / span * num_bands).astype(int)
    idx = np.clip(idx, 0, num_bands - 1)

    peak = np.full(num_bands, -np.inf, dtype=np.float64)
    total = np.zeros(num_bands, dtype=np.float64)
    count = np.zeros(num_bands, dtype=np.int64)
    for b in range(num_bands):
        sel = power_dbm[idx == b]
        if sel.size:
            peak[b] = float(np.max(sel))
            total[b] = float(np.sum(sel))
            count[b] = sel.size
    # Bands with no bins (very coarse grids) inherit the global minimum.
    fallback = float(np.min(power_dbm)) if n_bins else -120.0
    peak[~np.isfinite(peak)] = fallback
    mean = np.where(count > 0, total / np.maximum(count, 1), fallback)
    return peak, mean


def detect_hops(
    prev_active: np.ndarray, curr_active: np.ndarray, max_step: int = 6
) -> list[tuple[int, int]]:
    """Pair bands that switched off with nearby bands that switched on."""
    prev_active = np.asarray(prev_active, dtype=bool)
    curr_active = np.asarray(curr_active, dtype=bool)
    lost = list(np.nonzero(prev_active & ~curr_active)[0])
    gained = list(np.nonzero(curr_active & ~prev_active)[0])
    hops: list[tuple[int, int]] = []
    used_gained: set[int] = set()
    for lo in lost:
        best = None
        best_d = max_step + 1
        for ga in gained:
            if ga in used_gained:
                continue
            d = abs(int(ga) - int(lo))
            if d <= max_step and d < best_d:
                best, best_d = int(ga), d
        if best is not None:
            hops.append((int(lo), best))
            used_gained.add(best)
    return hops


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + float(np.exp(-x)))


class SweepProcessor:
    """Stateful frame -> observations pipeline (one per live session)."""

    def __init__(
        self,
        num_bands: int,
        *,
        threshold_db: float = 6.0,
        smoothing_alpha: float = 0.4,
        noise_percentile: float = 25.0,
    ) -> None:
        self.num_bands = int(num_bands)
        self.threshold_db = float(threshold_db)
        self.alpha = float(np.clip(smoothing_alpha, 0.01, 1.0))
        self.noise_percentile = float(noise_percentile)

        self._smoothed: np.ndarray | None = None
        self._prev_active = np.zeros(self.num_bands, dtype=bool)
        self.last_hops: list[tuple[int, int]] = []
        self.frames_processed = 0
        self.last_noise_floor_dbm = -120.0

    def ingest(self, frame: SweepFrame) -> list[BandObservation]:
        power = np.asarray(frame.power_dbm, dtype=np.float64)
        peak, mean = bins_to_bands(
            power,
            frame.f_start_hz,
            frame.f_stop_hz,
            frame.bin_hz,
            self.num_bands,
        )

        if self._smoothed is None:
            self._smoothed = peak.copy()
        else:
            self._smoothed = (
                self.alpha * peak + (1.0 - self.alpha) * self._smoothed
            )

        noise_floor = estimate_noise_floor(power, self.noise_percentile)
        self.last_noise_floor_dbm = noise_floor

        snr = self._smoothed - noise_floor
        active = snr > self.threshold_db

        self.last_hops = detect_hops(self._prev_active, active)
        self._prev_active = active.copy()
        self.frames_processed += 1

        obs: list[BandObservation] = []
        for b in range(self.num_bands):
            obs.append(
                BandObservation(
                    band=b,
                    active=bool(active[b]),
                    power_dbm=round(float(self._smoothed[b]), 3),
                    noise_floor_dbm=round(float(noise_floor), 3),
                    snr_db=round(float(snr[b]), 3),
                    confidence=round(
                        _sigmoid((float(snr[b]) - self.threshold_db) / 3.0), 4
                    ),
                )
            )
        return obs
