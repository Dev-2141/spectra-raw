"""Scheduler interface.

A scheduler sees only what a real receive-only sensor could know: its own visit
history, past detections, rewards, and static library-style threat priors. It
never reads the ground-truth occupancy matrix.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models.core import ScanDecision


class BaseScheduler(ABC):
    """Base class for all scan schedulers."""

    name: str = "base"

    def __init__(self, num_bands: int, rng, params: dict | None = None):
        self.num_bands = num_bands
        self.rng = rng
        self.params = params or {}

    # ------------------------------------------------------------------ #
    @abstractmethod
    def decide(self, context: "SchedulerContext") -> ScanDecision:  # noqa: F821
        """Choose the next band to scan and explain why."""

    def update(self, feedback: "ScanFeedback") -> None:  # noqa: F821
        """Learn from the outcome of the last scan. Baselines ignore this."""

    def reset(self) -> None:
        """Clear any learned state."""

    # ------------------------------------------------------------------ #
    def _decision(
        self,
        *,
        context,
        band: int,
        confidence: float = 0.0,
        predicted_active: bool | None = None,
        reasons: list[str] | None = None,
        alternatives: list[int] | None = None,
        explanation: str = "",
    ) -> ScanDecision:
        return ScanDecision(
            time_slot=context.time_slot,
            selected_band=int(band),
            scheduler=self.name,
            confidence=float(max(0.0, min(1.0, confidence))),
            predicted_active=predicted_active,
            reasons=(reasons or [])[:3],
            alternatives=[int(b) for b in (alternatives or [])][:3],
            explanation=explanation,
        )
