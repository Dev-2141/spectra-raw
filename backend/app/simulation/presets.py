"""Example scenario presets.

Each preset is a named, reproducible scenario: an environment config (with an
emitter-behaviour mix), a receiver config, and a short description of what it
stresses and which scheduler family it favours. Descriptions live here in code
/ config, not in a marketing page.
"""

from __future__ import annotations

from ..models.core import RFEnvironmentConfig, ReceiverConfig

_PRESETS: dict[str, dict] = {
    "Sparse Environment": {
        "description": (
            "Wide 96-band spectrum, very few emitters, short low-duty emissions. "
            "Coverage and revisit timing dominate; an adaptive revisit beats a "
            "slow linear sweep."
        ),
        "environment": RFEnvironmentConfig(
            num_bands=96,
            num_time_slots=1200,
            emitter_density=0.06,
            noise_floor_db=-101.0,
            snr_min_db=6.0,
            snr_max_db=20.0,
            high_priority_fraction=0.2,
            behavior_weights={"low_duty": 0.4, "burst": 0.3, "periodic": 0.2, "priority": 0.1},
            seed=4101,
        ),
        "receiver": ReceiverConfig(detection_threshold_db=5.0, retune_delay_slots=1),
    },
    "Dense Emitter Environment": {
        "description": (
            "64 bands packed with constant and bursty emitters. Many bands are "
            "active at once, so threat- and hit-rate-weighted prioritisation "
            "pays off over blind cycling."
        ),
        "environment": RFEnvironmentConfig(
            num_bands=64,
            num_time_slots=1000,
            emitter_density=0.55,
            noise_floor_db=-100.0,
            snr_min_db=5.0,
            snr_max_db=18.0,
            high_priority_fraction=0.18,
            behavior_weights={"constant": 0.4, "burst": 0.3, "periodic": 0.2, "priority": 0.1},
            seed=4202,
        ),
        "receiver": ReceiverConfig(detection_threshold_db=6.0, retune_delay_slots=1),
    },
    "Frequency Hopping Challenge": {
        "description": (
            "Emitters roam across bands every few slots. A fixed sweep chronically "
            "misses them; bandit and priority schedulers that chase recent "
            "activity catch far more."
        ),
        "environment": RFEnvironmentConfig(
            num_bands=64,
            num_time_slots=1000,
            emitter_density=0.2,
            noise_floor_db=-100.0,
            snr_min_db=6.0,
            snr_max_db=20.0,
            high_priority_fraction=0.25,
            behavior_weights={"hopping": 0.6, "burst": 0.22, "priority": 0.18},
            seed=4303,
        ),
        "receiver": ReceiverConfig(detection_threshold_db=6.0, retune_delay_slots=2),
    },
    "Periodic Radar-Like Challenge": {
        "description": (
            "Mostly periodic pulse trains with fixed intervals. The priority "
            "scheduler's period estimator can predict the next emission and be "
            "parked on the band when it fires."
        ),
        "environment": RFEnvironmentConfig(
            num_bands=48,
            num_time_slots=1000,
            emitter_density=0.22,
            noise_floor_db=-100.0,
            snr_min_db=7.0,
            snr_max_db=21.0,
            high_priority_fraction=0.2,
            behavior_weights={"periodic": 0.7, "constant": 0.15, "priority": 0.15},
            seed=4404,
        ),
        "receiver": ReceiverConfig(detection_threshold_db=7.0, retune_delay_slots=1),
    },
    "High-Threat Low-Duty Challenge": {
        "description": (
            "Rare, short, high-value intermittent emissions on an 80-band span. "
            "Half the emitters are high priority; threat-weighted scoring lifts "
            "the high-priority detection rate well above a baseline sweep."
        ),
        "environment": RFEnvironmentConfig(
            num_bands=80,
            num_time_slots=1200,
            emitter_density=0.12,
            noise_floor_db=-101.0,
            snr_min_db=6.0,
            snr_max_db=19.0,
            high_priority_fraction=0.5,
            behavior_weights={"priority": 0.45, "low_duty": 0.35, "burst": 0.2},
            seed=4505,
        ),
        "receiver": ReceiverConfig(detection_threshold_db=5.0, retune_delay_slots=1),
    },
    "Noisy Spectrum Challenge": {
        "description": (
            "High noise floor, low SNR, elevated false-alarm rate and a noisier "
            "SNR estimate. Detection is hard and empty scans are costly; "
            "conservative revisit plus activity prediction hold up best."
        ),
        "environment": RFEnvironmentConfig(
            num_bands=64,
            num_time_slots=1000,
            emitter_density=0.2,
            noise_floor_db=-90.0,
            snr_min_db=4.0,
            snr_max_db=14.0,
            high_priority_fraction=0.2,
            behavior_weights={"burst": 0.3, "periodic": 0.25, "constant": 0.25, "priority": 0.2},
            seed=4606,
        ),
        "receiver": ReceiverConfig(
            detection_threshold_db=8.0,
            retune_delay_slots=2,
            snr_measurement_noise_db=3.5,
            false_alarm_prob=0.05,
        ),
    },
}


def list_presets() -> list[dict]:
    out = []
    for name, p in _PRESETS.items():
        out.append(
            {
                "name": name,
                "description": p["description"],
                "environment": p["environment"].model_dump(),
                "receiver": p["receiver"].model_dump(),
            }
        )
    return out


def get_preset(name: str) -> tuple[RFEnvironmentConfig, ReceiverConfig]:
    if name not in _PRESETS:
        raise KeyError(
            f"unknown preset '{name}'. Available: {', '.join(_PRESETS)}"
        )
    p = _PRESETS[name]
    # return copies so callers can mutate freely
    return p["environment"].model_copy(deep=True), p["receiver"].model_copy(deep=True)


def preset_names() -> list[str]:
    return list(_PRESETS.keys())
