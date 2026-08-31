"""Parametric emitter model (Extension Step 3).

A scenario editor builds :class:`EmitterSpec` objects; :func:`paint_specs` writes
them into the environment's ground-truth matrices. Frequency agility, PRI stagger,
antenna patterns and (for movers) range-dependent propagation are all handled
here. The legacy random-behaviour generator in ``environment.py`` is untouched
and still runs whenever a config has no ``emitter_specs``.
"""

from __future__ import annotations

import numpy as np

from ..models.core import EmitterSpec
from . import propagation as prop


# --------------------------------------------------------------------------- #
# PRI (pulse repetition interval) models
# --------------------------------------------------------------------------- #
def pri_pulse_times(spec: EmitterSpec, total_slots: int, rng: np.random.Generator) -> list[int]:
    """Start slots of each pulse for a ``periodic`` emitter under its PRI model."""
    T = total_slots
    t = int(spec.phase_slots) % max(1, spec.period_slots)
    out: list[int] = []
    model = spec.pri_model
    stagger = list(spec.pri_stagger) if spec.pri_stagger else []
    si = 0
    dwell_start = t
    dwell_long = False

    while t < T:
        out.append(t)
        if model == "jitter":
            j = int(rng.integers(-spec.pri_jitter_slots, spec.pri_jitter_slots + 1))
            gap = max(1, spec.period_slots + j)
        elif model == "stagger" and stagger:
            gap = max(1, int(stagger[si % len(stagger)]))
            si += 1
        elif model == "dwell_switch":
            if t - dwell_start >= spec.pri_dwell_slots:
                dwell_long = not dwell_long
                dwell_start = t
            gap = max(1, spec.period_slots * (2 if dwell_long else 1))
        else:  # fixed
            gap = max(1, spec.period_slots)
        t += gap
    return out


# --------------------------------------------------------------------------- #
# Antenna pattern
# --------------------------------------------------------------------------- #
def _wrap_deg(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


def antenna_gain_db(pattern, t: int) -> float:
    """Gain (dB) toward the receiver (assumed at bearing 0) at slot ``t``."""
    kind = getattr(pattern, "kind", "omni")
    peak = float(pattern.peak_gain_db)
    if kind == "omni":
        return peak
    half = max(1.0, float(pattern.beamwidth_deg) / 2.0)
    if kind == "sector":
        off = abs(_wrap_deg(float(pattern.boresight_deg)))
        return peak if off <= half else peak + float(pattern.backlobe_db)
    if kind == "rotating":
        period = max(1, int(pattern.rotation_period_slots))
        boresight = (t / period) * 360.0
        off = abs(_wrap_deg(boresight))
        return peak if off <= half else peak + float(pattern.backlobe_db)
    return peak


# --------------------------------------------------------------------------- #
# Frequency agility
# --------------------------------------------------------------------------- #
def band_at(spec: EmitterSpec, t: int, num_bands: int, hop_seq: list[int] | None) -> int:
    a = spec.agility
    if a == "list_hop" and spec.hop_bands:
        step = t // max(1, spec.hop_interval_slots)
        return int(spec.hop_bands[step % len(spec.hop_bands)]) % num_bands
    if a == "random_hop" and hop_seq:
        step = t // max(1, spec.hop_interval_slots)
        return int(hop_seq[step % len(hop_seq)]) % num_bands
    if a == "sweep":
        step = t // max(1, spec.hop_interval_slots)
        span = max(1, spec.sweep_span_bands)
        tri = step % (2 * span)
        offset = tri if tri < span else (2 * span - tri)
        return int(np.clip(spec.home_band + offset, 0, num_bands - 1))
    return int(np.clip(spec.home_band, 0, num_bands - 1))


# --------------------------------------------------------------------------- #
# Propagation / Doppler helpers (mover-aware)
# --------------------------------------------------------------------------- #
def radial_speed_kms(spec: EmitterSpec, t: int, total_slots: int, dt: int = 1) -> float:
    """Closing speed toward the receiver at origin (positive => approaching)."""
    x0, y0 = prop.position_at(t, total_slots, spec.kinematics)
    x1, y1 = prop.position_at(min(t + dt, total_slots - 1), total_slots, spec.kinematics)
    r0 = prop.range_km(x0, y0)
    r1 = prop.range_km(x1, y1)
    return float(-(r1 - r0) / max(dt, 1))


def emitter_doppler_hz(spec: EmitterSpec, t: int, total_slots: int, freq_mhz: float) -> float:
    return prop.doppler_hz(radial_speed_kms(spec, t, total_slots), freq_mhz)


def received_snr_db(
    spec: EmitterSpec,
    t: int,
    total_slots: int,
    rng: np.random.Generator,
    *,
    freq_mhz: float = 300.0,
    terrain_mask: np.ndarray | None = None,
    band: int | None = None,
    fading: str = "rayleigh",
) -> float:
    """Nominal SNR adjusted for antenna gain, range loss and fading."""
    snr = float(spec.snr_db) + float(spec.erp_db) + antenna_gain_db(spec.antenna, t)
    kin = spec.kinematics
    moving = kin.kind == "waypoint" or (kin.x_km or kin.y_km)
    if moving:
        x, y = prop.position_at(t, total_slots, kin)
        r = max(prop.range_km(x, y), 0.1)
        ref = 10.0
        snr -= prop.log_distance_loss_db(r, freq_mhz) - prop.log_distance_loss_db(ref, freq_mhz)
    if band is not None:
        snr -= prop.terrain_mask_db(terrain_mask, band)
    if fading and fading != "none":
        snr += prop.fading_db(rng, fading)
    return float(snr)


# --------------------------------------------------------------------------- #
# On/off intervals
# --------------------------------------------------------------------------- #
def _on_intervals(spec: EmitterSpec, T: int, rng: np.random.Generator) -> list[tuple[int, int]]:
    duty = spec.duty
    out: list[tuple[int, int]] = []
    if duty == "periodic":
        for start in pri_pulse_times(spec, T, rng):
            out.append((start, min(T - 1, start + max(1, spec.pulse_slots) - 1)))
    elif duty == "bursts":
        t = 0
        while t < T:
            t += int(rng.integers(6, 34))
            b = int(rng.integers(1, 5))
            out.append((t, min(T - 1, t + b - 1)))
            t += b
    elif duty == "low_duty":
        n = max(1, int(T * float(rng.uniform(0.01, 0.04))))
        for _ in range(n):
            s = int(rng.integers(0, T))
            out.append((s, min(T - 1, s + int(rng.integers(1, 3)) - 1)))
    else:  # blocks
        t = int(rng.integers(0, max(1, spec.period_slots)))
        while t < T:
            on = max(2, spec.period_slots)
            out.append((t, min(T - 1, t + on - 1)))
            t += on + max(1, spec.period_slots // 3)
    return [(a, b) for a, b in out if b >= a]


# --------------------------------------------------------------------------- #
# Painter
# --------------------------------------------------------------------------- #
def paint_specs(
    *,
    occupancy: np.ndarray,
    snr_db: np.ndarray,
    power_db: np.ndarray,
    threat: np.ndarray,
    emitter_id_matrix: np.ndarray,
    specs: list[EmitterSpec],
    noise_floor_db: float,
    seed: int,
    terrain_mask: np.ndarray | None = None,
) -> list[dict]:
    """Write parametric emitters into the ground-truth matrices in place.

    Returns lightweight per-emitter metadata dicts for the API.
    """
    T, B = occupancy.shape
    meta: list[dict] = []
    for i, spec in enumerate(specs):
        rng = np.random.default_rng(seed * 1_000_003 + i * 7919 + 17)
        hop_seq = None
        if spec.agility == "random_hop":
            n_steps = max(1, T // max(1, spec.hop_interval_slots)) + 2
            hop_seq = [int(rng.integers(0, B)) for _ in range(n_steps)]

        touched_bands: set[int] = set()
        for (t0, t1) in _on_intervals(spec, T, rng):
            for t in range(t0, t1 + 1):
                band = band_at(spec, t, B, hop_seq)
                touched_bands.add(band)
                snr = received_snr_db(spec, t, T, rng, band=band, terrain_mask=terrain_mask)
                if (not occupancy[t, band]) or snr > snr_db[t, band]:
                    occupancy[t, band] = True
                    snr_db[t, band] = np.float32(snr)
                    power_db[t, band] = np.float32(noise_floor_db + snr)
                    threat[t, band] = np.float32(spec.threat)
                    emitter_id_matrix[t, band] = np.int32(spec.id if spec.id else i)

        if spec.agility != "fixed":
            behavior = "hopping"
        elif spec.high_priority or spec.threat >= 0.7:
            behavior = "priority"
        else:
            behavior = {
                "blocks": "constant",
                "periodic": "periodic",
                "bursts": "burst",
                "low_duty": "low_duty",
            }.get(spec.duty, "constant")

        meta.append(
            {
                "id": spec.id if spec.id else i,
                "label": spec.label or f"S{i:02d}-{spec.agility}-{spec.duty}",
                "behavior": behavior,
                "home_band": int(spec.home_band),
                "threat": round(float(spec.threat), 3),
                "high_priority": bool(spec.high_priority or spec.threat >= 0.7),
                "snr_db": round(float(spec.snr_db), 2),
                "duty_cycle": round(float(occupancy[:, spec.home_band % B].mean()), 4),
                "params": {
                    "agility": spec.agility,
                    "pri_model": spec.pri_model,
                    "modulation": spec.modulation,
                    "antenna": spec.antenna.kind,
                    "bands_touched": sorted(touched_bands)[:16],
                },
            }
        )
    return meta
