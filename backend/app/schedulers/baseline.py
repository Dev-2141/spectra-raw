"""Baseline (open-loop) schedulers: round-robin and random.

These do not learn. They exist as the comparison floor that the smart
schedulers in Step 2 must beat.
"""

from __future__ import annotations

from ..models.core import ScanDecision
from .base import BaseScheduler


class RoundRobinScheduler(BaseScheduler):
    """Sweep every band in order, forever. Classic open-loop scan."""

    name = "round_robin"

    def __init__(self, num_bands: int, rng, params: dict | None = None):
        super().__init__(num_bands, rng, params)
        self._next = int(self.params.get("start_band", 0)) % num_bands

    def reset(self) -> None:
        self._next = int(self.params.get("start_band", 0)) % self.num_bands

    def decide(self, context) -> ScanDecision:
        band = self._next
        self._next = (self._next + 1) % self.num_bands
        return self._decision(
            context=context,
            band=band,
            confidence=1.0 / self.num_bands,
            reasons=[
                "fixed sequential sweep",
                f"position {band + 1}/{self.num_bands} in cycle",
                "no adaptation to activity",
            ],
            alternatives=[(band + 1) % self.num_bands, (band + 2) % self.num_bands],
            explanation=(
                f"Round-robin sweep: scan band {band}, then advance. "
                "Ignores hits, misses, and threat."
            ),
        )


class RandomScheduler(BaseScheduler):
    """Pick a uniformly random band each dwell."""

    name = "random"

    def decide(self, context) -> ScanDecision:
        band = int(self.rng.integers(0, self.num_bands))
        alts = [int(self.rng.integers(0, self.num_bands)) for _ in range(2)]
        return self._decision(
            context=context,
            band=band,
            confidence=1.0 / self.num_bands,
            reasons=[
                "uniform random selection",
                "memoryless",
                "no threat weighting",
            ],
            alternatives=alts,
            explanation=f"Random scheduler: uniformly sampled band {band}.",
        )
