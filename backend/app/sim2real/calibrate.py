"""Fit sim parameters to a recording's spectrum statistics."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ..config import get_settings
from ..dsp.process import SweepProcessor
from ..hardware.recordings import get_recording_meta, iter_recording_frames
from ..models.core import CalibrationProfile


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _profiles_dir() -> Path:
    d = get_settings().data_dir / "sim2real"
    d.mkdir(parents=True, exist_ok=True)
    return d


def calibrate(recording_id: str, name: str | None = None, num_bands: int = 48) -> CalibrationProfile:
    meta = get_recording_meta(recording_id)  # raises KeyError
    proc = SweepProcessor(num_bands)
    occ_rates: list[float] = []
    snr_active: list[float] = []
    noise_floors: list[float] = []
    frames = 0
    for frame in iter_recording_frames(recording_id):
        obs = proc.ingest(frame)
        frames += 1
        active = [o for o in obs if o.active]
        occ_rates.append(len(active) / max(1, len(obs)))
        noise_floors.append(obs[0].noise_floor_dbm if obs else -100.0)
        snr_active.extend(o.snr_db for o in active)

    if frames == 0:
        raise ValueError(f"recording {recording_id} has no frames")

    noise_floor = float(np.median(noise_floors))
    occ = float(np.mean(occ_rates))
    if snr_active:
        snr_lo = float(np.percentile(snr_active, 10))
        snr_hi = float(np.percentile(snr_active, 90))
    else:
        snr_lo, snr_hi = 4.0, 16.0
    # crude false-alarm proxy: fraction of "active" bands with SNR barely over threshold
    borderline = [s for s in snr_active if s < proc.threshold_db + 2.0]
    far = float(len(borderline) / max(1, len(snr_active))) * 0.1

    profile = CalibrationProfile(
        profile_id=f"cal_{uuid.uuid4().hex[:10]}",
        name=name or f"cal:{meta.name}",
        recording_id=recording_id,
        created_at=_utc(),
        num_bands=num_bands,
        noise_floor_db=round(noise_floor, 2),
        emitter_density=round(float(np.clip(occ * num_bands / max(num_bands, 1) * 3.0, 0.02, 0.9)), 3),
        snr_min_db=round(max(snr_lo, 2.0), 2),
        snr_max_db=round(max(snr_hi, snr_lo + 2.0), 2),
        false_alarm_prob=round(float(np.clip(far, 0.0, 0.2)), 4),
        stats={
            "frames": frames,
            "mean_occupancy_rate": round(occ, 4),
            "median_noise_floor_dbm": round(noise_floor, 2),
            "snr_p10": round(snr_lo, 2),
            "snr_p90": round(snr_hi, 2),
        },
    )
    (_profiles_dir() / f"{profile.profile_id}.json").write_text(
        profile.model_dump_json(indent=2), "utf-8"
    )
    return profile


def list_profiles() -> list[CalibrationProfile]:
    out: list[CalibrationProfile] = []
    for f in sorted(_profiles_dir().glob("*.json")):
        try:
            out.append(CalibrationProfile(**json.loads(f.read_text("utf-8"))))
        except (ValueError, OSError):
            continue
    out.sort(key=lambda p: p.created_at, reverse=True)
    return out


def get_profile(profile_id: str) -> CalibrationProfile:
    path = _profiles_dir() / f"{profile_id}.json"
    if not path.is_file():
        raise KeyError(f"calibration profile not found: {profile_id}")
    return CalibrationProfile(**json.loads(path.read_text("utf-8")))
