"""Reality-gap: run one scheduler on the recording and on the calibrated sim,
report per-metric divergence + a short narrative.
"""

from __future__ import annotations

import numpy as np

from ..dsp.process import SweepProcessor
from ..hardware.recordings import iter_recording_frames
from ..models.core import (
    MetricGap,
    RealityGapReport,
    RFEnvironmentConfig,
    ReceiverConfig,
)
from ..simulation.engine import Simulation
from .calibrate import get_profile

_METRICS = ("occupancy_rate", "mean_snr_db", "detection_rate", "false_alarm_rate")


def _recording_stats(recording_id: str, num_bands: int) -> dict:
    proc = SweepProcessor(num_bands)
    occ, snr, fa_num, fa_den = [], [], 0, 0
    for frame in iter_recording_frames(recording_id):
        obs = proc.ingest(frame)
        active = [o for o in obs if o.active]
        occ.append(len(active) / max(1, len(obs)))
        snr.extend(o.snr_db for o in active)
        for o in obs:
            if not o.active:
                fa_den += 1
                if o.snr_db > proc.threshold_db - 1.0:
                    fa_num += 1
    return {
        "occupancy_rate": float(np.mean(occ)) if occ else 0.0,
        "mean_snr_db": float(np.mean(snr)) if snr else 0.0,
        "detection_rate": float(np.mean([1.0 if s > proc.threshold_db else 0.0 for s in snr])) if snr else 0.0,
        "false_alarm_rate": (fa_num / fa_den) if fa_den else 0.0,
    }


def _sim_stats(cfg: RFEnvironmentConfig, scheduler: str, steps: int) -> dict:
    sim = Simulation(cfg, ReceiverConfig(false_alarm_prob=0.02), scheduler)
    sim.run(steps)
    m = sim.metrics_snapshot()
    env = sim.env
    occ = float(env.occupancy[: min(steps, env.num_time_slots)].mean())
    snr_vals = env.snr_db[env.occupancy]
    return {
        "occupancy_rate": occ,
        "mean_snr_db": float(snr_vals.mean()) if snr_vals.size else 0.0,
        "detection_rate": float(m.probability_of_detection),
        "false_alarm_rate": float(m.false_alarm_rate),
    }


def compute_gap(
    recording_id: str,
    profile_id: str,
    scheduler: str = "priority",
    steps: int = 600,
    noise_shift_db: float = 0.0,
) -> RealityGapReport:
    profile = get_profile(profile_id)
    # A deliberate profile mismatch: a rise in noise floor the sim signals don't
    # follow lowers effective SNR and, with it, detectability.
    snr_penalty = 0.5 * float(noise_shift_db)
    cfg = RFEnvironmentConfig(
        num_bands=profile.num_bands,
        num_time_slots=steps + 20,
        noise_floor_db=profile.noise_floor_db + float(noise_shift_db),
        emitter_density=max(0.02, profile.emitter_density * (1.0 - 0.02 * noise_shift_db)),
        snr_min_db=max(2.0, profile.snr_min_db - snr_penalty),
        snr_max_db=max(4.0, profile.snr_max_db - snr_penalty),
        seed=4242,
    )

    rec = _recording_stats(recording_id, profile.num_bands)
    sim = _sim_stats(cfg, scheduler, steps)

    gaps: list[MetricGap] = []
    for k in _METRICS:
        rv, sv = float(rec[k]), float(sim[k])
        scale = max(abs(rv), abs(sv), 1.0)
        gaps.append(
            MetricGap(
                metric=k,
                recording_value=round(rv, 4),
                sim_value=round(sv, 4),
                gap=round(abs(rv - sv) / scale, 4),
            )
        )
    score = round(float(np.mean([g.gap for g in gaps])), 4)

    worst = max(gaps, key=lambda g: g.gap)
    if score < 0.15:
        note = "calibrated sim closely reproduces the recording's statistics"
    elif score < 0.4:
        note = f"moderate divergence; largest on {worst.metric} ({worst.gap})"
    else:
        note = (
            f"large reality gap (score {score}); {worst.metric} differs by "
            f"{worst.gap} — recalibrate or widen the sim model"
        )
    return RealityGapReport(
        recording_id=recording_id,
        profile_id=profile_id,
        scheduler=scheduler,
        steps=steps,
        metrics=gaps,
        gap_score=score,
        narrative=note,
    )
