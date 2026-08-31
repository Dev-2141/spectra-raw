"""Preset curriculum: train across scenarios in increasing difficulty."""

from __future__ import annotations

from ..simulation.presets import _PRESETS

# rough difficulty order (sparse/easy -> noisy/hard)
CURRICULUM_ORDER = [
    "Sparse Environment",
    "Periodic Radar-Like Challenge",
    "Dense Emitter Environment",
    "High-Threat Low-Duty Challenge",
    "Frequency Hopping Challenge",
    "Noisy Spectrum Challenge",
]


def curriculum_stages() -> list[str]:
    return [n for n in CURRICULUM_ORDER if n in _PRESETS]
