"""Simulated EW effects (Extension Step 3).

SIMULATION ONLY. Every function here works purely on NumPy matrices that model
*what our receiver observes*. It never produces RF, never touches a device, and
never imports ``app.hardware`` (enforced by ``test_ext_step3.py``).

An effect models an adversary transmitter's impact — jamming, a repeater, a
spoofed track — as an overlay on the observed spectrum. Ground truth
(``occupancy_truth`` / ``snr_truth``) is snapshotted first and left untouched, so
"did the scheduler still detect the real signal under jamming?" and "was it
deceived by a spoof?" are both measurable.
"""

from __future__ import annotations

import numpy as np

from ..models.core import EWEffectSpec

# This module must remain free of any hardware / transmit dependency.
_FORBIDDEN_IMPORT = "app.hardware"


def _clip_span(spec: EWEffectSpec, T: int, B: int) -> tuple[int, int, int, int]:
    t0 = max(0, int(spec.start_slot))
    t1 = min(T - 1, int(spec.stop_slot))
    b0 = max(0, min(B - 1, int(spec.band_lo)))
    b1 = max(b0, min(B - 1, int(spec.band_hi if spec.band_hi else spec.band_lo)))
    return t0, t1, b0, b1


def apply_effects(env, effects: list[EWEffectSpec]) -> None:
    """Populate ``env.*_observed`` / ``is_synthetic_effect`` from a truth env."""
    T, B = env.occupancy.shape

    occ_truth = env.occupancy.astype(bool).copy()
    snr_truth = env.snr_db.astype(np.float32).copy()
    pow_truth = env.power_db.astype(np.float32).copy()

    env.occupancy_truth = occ_truth
    env.snr_truth = snr_truth
    env.power_truth = pow_truth

    occ_obs = occ_truth.copy()
    snr_obs = snr_truth.copy()
    pow_obs = pow_truth.copy()
    noise_map = np.full((T, B), float(env.noise_floor_db), dtype=np.float32)
    synth = np.zeros((T, B), dtype=bool)
    labels: list[dict] = []

    for k, spec in enumerate(effects):
        t0, t1, b0, b1 = _clip_span(spec, T, B)
        excess = float(spec.power_db)

        if spec.kind in ("barrage_noise", "spot_jam"):
            noise_map[t0 : t1 + 1, b0 : b1 + 1] += excess
            # real signals in-band lose SNR by the jam excess
            region_snr = snr_obs[t0 : t1 + 1, b0 : b1 + 1]
            snr_obs[t0 : t1 + 1, b0 : b1 + 1] = np.maximum(region_snr - excess, -20.0)
            if spec.kind == "spot_jam":
                # jammer energy shows up as observed occupancy on the band
                occ_obs[t0 : t1 + 1, b0 : b1 + 1] = True
                pow_obs[t0 : t1 + 1, b0 : b1 + 1] = np.float32(
                    env.noise_floor_db + excess
                )
            synth[t0 : t1 + 1, b0 : b1 + 1] = True

        elif spec.kind == "swept_jam":
            width = max(1, b1 - b0 + 1)
            for t in range(t0, t1 + 1):
                jb = b0 + int((t - t0) * float(spec.sweep_rate_bands_per_slot)) % width
                noise_map[t, jb] += excess
                snr_obs[t, jb] = max(float(snr_obs[t, jb]) - excess, -20.0)
                occ_obs[t, jb] = True
                pow_obs[t, jb] = np.float32(env.noise_floor_db + excess)
                synth[t, jb] = True

        elif spec.kind == "repeater_ghost":
            src = max(0, min(B - 1, int(spec.source_band)))
            tgt = max(0, min(B - 1, int(spec.target_band or spec.band_lo)))
            delay = max(0, int(spec.delay_slots))
            for t in range(t0, t1 + 1):
                if occ_truth[t, src] and t + delay <= t1:
                    tt = t + delay
                    occ_obs[tt, tgt] = True
                    snr_obs[tt, tgt] = np.float32(
                        max(float(snr_obs[tt, tgt]), float(spec.spoof_snr_db))
                    )
                    pow_obs[tt, tgt] = np.float32(
                        env.noise_floor_db + float(spec.spoof_snr_db)
                    )
                    synth[tt, tgt] = True

        elif spec.kind == "spoof_track":
            tgt = max(0, min(B - 1, int(spec.target_band or spec.band_lo)))
            period = max(2, int(spec.spoof_period_slots))
            pulse = max(1, int(spec.spoof_pulse_slots))
            for start in range(t0, t1 + 1, period):
                for tt in range(start, min(t1, start + pulse - 1) + 1):
                    occ_obs[tt, tgt] = True
                    snr_obs[tt, tgt] = np.float32(float(spec.spoof_snr_db))
                    pow_obs[tt, tgt] = np.float32(
                        env.noise_floor_db + float(spec.spoof_snr_db)
                    )
                    synth[tt, tgt] = True

        labels.append(
            {
                "index": k,
                "kind": spec.kind,
                "label": spec.label or spec.kind,
                "start_slot": t0,
                "stop_slot": t1,
                "band_lo": b0,
                "band_hi": b1,
            }
        )

    env.occupancy_observed = occ_obs
    env.snr_observed = snr_obs
    env.power_observed = pow_obs
    env.noise_floor_map = noise_map
    env.is_synthetic_effect = synth
    env.effect_labels = labels
