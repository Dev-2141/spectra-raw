"""Digital signal processing for the live receive path.

Pure NumPy. Turns a :class:`SweepFrame` (power vs frequency) into a list of
:class:`BandObservation` (per-band active / power / SNR) that the existing
schedulers can consume unchanged.
"""

from .process import (
    SweepProcessor,
    bins_to_bands,
    detect_hops,
    estimate_noise_floor,
)

__all__ = [
    "SweepProcessor",
    "bins_to_bands",
    "detect_hops",
    "estimate_noise_floor",
]
