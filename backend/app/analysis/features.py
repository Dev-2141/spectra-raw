"""Per-track feature extraction.

Given the contiguous activity runs of one emitter track (each a
``(start, end, band)`` triple) plus the SNR samples, derive the descriptors the
classifier and the library matcher consume. Pure / deterministic.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


@dataclass
class TrackFeatures:
    run_count: int
    active_slots: int
    first_seen: int
    last_seen: int
    span_slots: int
    duty_cycle: float
    pulse_width_mean: float
    pulse_width_std: float
    pri_estimate: float
    pri_jitter: float          # std(gap) / mean(gap), 0 == perfectly regular
    n_bands: int
    bandwidth_bands: int
    hop_rate: float            # band changes per active slot
    hop_pattern: str           # fixed | list | sweep | random
    snr_mean_db: float
    snr_std_db: float
    spectral_shape: str        # narrow-pulsed | narrow-cw | wide-pulsed | wide-cw

    def as_dict(self) -> dict:
        return asdict(self)

    def vector(self) -> list[float]:
        """Ordered numeric vector for the classifier."""
        return [
            float(self.run_count),
            float(self.duty_cycle),
            float(self.pri_estimate),
            float(self.pri_jitter),
            float(self.hop_rate),
            float(self.n_bands),
            float(self.pulse_width_mean),
            float(self.span_slots and self.active_slots / self.span_slots),
            float(self.snr_mean_db),
            float(self.bandwidth_bands),
        ]


FEATURE_NAMES = [
    "run_count", "duty_cycle", "pri_estimate", "pri_jitter", "hop_rate",
    "n_bands", "pulse_width_mean", "active_fraction", "snr_mean_db",
    "bandwidth_bands",
]


def runs_from_occupancy(
    occ: np.ndarray, up_to_t: int, bands: list[int] | None = None
) -> dict[int, list[tuple[int, int]]]:
    """Collapse an occupancy matrix into per-band ``(start, end)`` activity runs."""
    T = min(up_to_t + 1, occ.shape[0])
    B = occ.shape[1]
    band_range = bands if bands is not None else range(B)
    out: dict[int, list[tuple[int, int]]] = {}
    for b in band_range:
        col = occ[:T, b].astype(bool)
        if not col.any():
            continue
        runs: list[tuple[int, int]] = []
        t = 0
        while t < T:
            if not col[t]:
                t += 1
                continue
            s = t
            while t < T and col[t]:
                t += 1
            runs.append((s, t - 1))
        out[b] = runs
    return out


def _hop_pattern(band_seq: list[int]) -> str:
    if len(set(band_seq)) <= 1:
        return "fixed"
    uniq = sorted(set(band_seq))
    if len(uniq) <= 4:
        return "list"
    diffs = np.diff(band_seq)
    if np.all(diffs >= 0) or np.all(diffs <= 0):
        return "sweep"
    # mostly small consistent steps -> sweep-ish; else random
    step_std = float(np.std(np.abs(diffs))) if len(diffs) else 0.0
    return "sweep" if step_std < 1.5 else "random"


def extract_features(
    runs_by_band: dict[int, list[tuple[int, int]]],
    snr_by_band: dict[int, float] | None = None,
) -> TrackFeatures:
    all_runs: list[tuple[int, int, int]] = []
    for b, runs in runs_by_band.items():
        for s, e in runs:
            all_runs.append((s, e, b))
    all_runs.sort()

    if not all_runs:
        return TrackFeatures(
            0, 0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0, 0.0, "fixed", 0.0, 0.0,
            "narrow-cw",
        )

    first_seen = all_runs[0][0]
    last_seen = max(e for _, e, _ in all_runs)
    span = max(1, last_seen - first_seen + 1)
    widths = np.array([e - s + 1 for s, e, _ in all_runs], dtype=float)
    active_slots = int(widths.sum())

    starts = np.array([s for s, _, _ in all_runs], dtype=float)
    gaps = np.diff(starts)
    gaps = gaps[gaps > 0]
    if gaps.size:
        pri = float(np.median(gaps))
        jitter = float(np.std(gaps) / max(np.mean(gaps), 1e-6))
    else:
        pri, jitter = 0.0, 0.0

    band_seq = [b for _, _, b in all_runs]
    uniq_bands = sorted(set(band_seq))
    n_bands = len(uniq_bands)
    bandwidth = uniq_bands[-1] - uniq_bands[0] + 1
    band_changes = int(np.count_nonzero(np.diff(band_seq))) if len(band_seq) > 1 else 0
    hop_rate = band_changes / max(active_slots, 1)
    pattern = _hop_pattern(band_seq)

    snrs = [snr_by_band.get(b, 0.0) for b in uniq_bands] if snr_by_band else [0.0]
    snr_mean = float(np.mean(snrs))
    snr_std = float(np.std(snrs))

    duty = active_slots / span
    wide = bandwidth >= 4 or n_bands >= 4
    pulsed = widths.mean() <= 4 and duty < 0.6
    shape = f"{'wide' if wide else 'narrow'}-{'pulsed' if pulsed else 'cw'}"

    return TrackFeatures(
        run_count=len(all_runs),
        active_slots=active_slots,
        first_seen=first_seen,
        last_seen=last_seen,
        span_slots=span,
        duty_cycle=round(duty, 4),
        pulse_width_mean=round(float(widths.mean()), 3),
        pulse_width_std=round(float(widths.std()), 3),
        pri_estimate=round(pri, 3),
        pri_jitter=round(jitter, 4),
        n_bands=n_bands,
        bandwidth_bands=int(bandwidth),
        hop_rate=round(hop_rate, 4),
        hop_pattern=pattern,
        snr_mean_db=round(snr_mean, 2),
        snr_std_db=round(snr_std, 2),
        spectral_shape=shape,
    )
