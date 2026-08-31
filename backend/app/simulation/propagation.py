"""Synthetic RF propagation helpers (Extension Step 3).

Deterministic given inputs. Used by the parametric emitter painter to turn an
emitter's nominal SNR into a received SNR that depends on range, a terrain/clutter
mask, small-scale fading and (for movers) a Doppler shift. Nothing here is
required by the legacy random-behaviour generator; it only engages when a
scenario supplies parametric emitters with positions.
"""

from __future__ import annotations

import numpy as np

_C_KMS = 299_792.458  # speed of light, km/s


def free_space_loss_db(distance_km: float, freq_mhz: float) -> float:
    """Free-space path loss (Friis). Clamped at 1 m to stay finite."""
    d = max(float(distance_km), 1e-3)
    f = max(float(freq_mhz), 1e-3)
    return 32.44 + 20.0 * np.log10(d) + 20.0 * np.log10(f)


def log_distance_loss_db(
    distance_km: float, freq_mhz: float, exponent: float = 3.0, d0_km: float = 0.1
) -> float:
    """Log-distance model: FSPL to a reference range, then ``10n·log10(d/d0)``."""
    d = max(float(distance_km), d0_km)
    ref = free_space_loss_db(d0_km, freq_mhz)
    return ref + 10.0 * float(exponent) * np.log10(d / d0_km)


def terrain_mask_db(mask: np.ndarray | None, band: int) -> float:
    """Extra loss (dB, >=0) for a band from an optional per-band clutter mask."""
    if mask is None:
        return 0.0
    m = np.asarray(mask, dtype=float)
    if m.size == 0:
        return 0.0
    return float(max(0.0, m[int(band) % m.size]))


def fading_db(rng: np.random.Generator, kind: str = "rayleigh", k_factor_db: float = 6.0) -> float:
    """Small-scale fading as a dB offset (mean ~0, can be negative)."""
    if kind == "none":
        return 0.0
    if kind == "rician":
        k = 10.0 ** (k_factor_db / 10.0)
        s = np.sqrt(k / (k + 1.0))
        sigma = np.sqrt(1.0 / (2.0 * (k + 1.0)))
        re = s + sigma * rng.standard_normal()
        im = sigma * rng.standard_normal()
        amp = np.hypot(re, im)
    else:  # rayleigh
        amp = np.hypot(rng.standard_normal(), rng.standard_normal()) / np.sqrt(2.0)
    return float(20.0 * np.log10(max(amp, 1e-3)))


def doppler_hz(rel_speed_kms: float, freq_mhz: float) -> float:
    """Doppler shift (Hz). Positive => closing (approaching)."""
    return float(rel_speed_kms / _C_KMS * freq_mhz * 1e6)


def position_at(t: int, total_slots: int, kin) -> tuple[float, float]:
    """Emitter (x, y) km at slot ``t`` for a static or linear-waypoint mover."""
    if getattr(kin, "kind", "static") != "waypoint" or total_slots <= 1:
        return float(kin.x_km), float(kin.y_km)
    frac = min(max(t / (total_slots - 1), 0.0), 1.0)
    x = kin.x_km + frac * (kin.x2_km - kin.x_km)
    y = kin.y_km + frac * (kin.y2_km - kin.y_km)
    return float(x), float(y)


def range_km(x_km: float, y_km: float, rx_x_km: float = 0.0, rx_y_km: float = 0.0) -> float:
    return float(np.hypot(x_km - rx_x_km, y_km - rx_y_km))
