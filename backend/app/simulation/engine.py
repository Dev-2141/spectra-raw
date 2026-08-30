"""Simulation step engine.

Wires together the environment, receiver twin, a scheduler, the reward engine,
and the metrics tracker. One :meth:`Simulation.step` call = one receiver dwell.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..metrics.tracker import MetricsTracker
from ..models.core import (
    DetectionEvent,
    RFEnvironmentConfig,
    ReceiverConfig,
    ScanDecision,
    SchedulerMetrics,
    SimulationStepResult,
)
from ..schedulers.base import BaseScheduler
from ..schedulers.registry import create_scheduler
from .environment import RFEnvironment
from .receiver import Receiver
from .reward import HIGH_PRIORITY_THREAT, compute_reward


@dataclass
class SchedulerContext:
    """Everything a scheduler is allowed to see before choosing a band."""

    time_slot: int
    num_bands: int
    current_band: int
    retune_delay: int
    visit_counts: np.ndarray
    hit_counts: np.ndarray
    miss_counts: np.ndarray
    false_alarm_counts: np.ndarray
    last_visit_slot: np.ndarray            # -1 if never visited
    predicted_activity: np.ndarray         # running P(active) estimate per band
    band_threat_prior: np.ndarray          # static library-style threat prior
    recent_reward: float
    last_feedback: "ScanFeedback | None" = None


@dataclass
class ScanFeedback:
    """Outcome handed back to the scheduler after a dwell."""

    time_slot: int
    band: int
    true_active: bool
    detected: bool
    false_alarm: bool
    reward: float
    reward_breakdown: dict = field(default_factory=dict)
    predicted_active: bool | None = None


class Simulation:
    """One reproducible scenario run."""

    def __init__(
        self,
        env_config: RFEnvironmentConfig,
        receiver_config: ReceiverConfig,
        scheduler_name: str,
        scheduler_params: dict | None = None,
        scheduler_instance: BaseScheduler | None = None,
    ):
        self.env_config = env_config
        self.receiver_config = receiver_config
        self.scheduler_name = scheduler_name
        self.scheduler_params = scheduler_params or {}

        # Independent RNG streams so scheduler noise doesn't perturb the world.
        self._seed = env_config.seed
        self.env = RFEnvironment(env_config)
        self.receiver = Receiver(
            receiver_config, np.random.default_rng(self._seed + 101)
        )
        # A supplied instance keeps its learned state across episodes (training).
        self.scheduler: BaseScheduler = scheduler_instance or create_scheduler(
            scheduler_name,
            env_config.num_bands,
            np.random.default_rng(self._seed + 202),
            self.scheduler_params,
        )
        self.metrics = MetricsTracker(self.env)

        self.t = 0
        self.done = False
        self.history: list[SimulationStepResult] = []

        B = env_config.num_bands
        self.visit_counts = np.zeros(B, dtype=np.int64)
        self.hit_counts = np.zeros(B, dtype=np.int64)
        self.miss_counts = np.zeros(B, dtype=np.int64)
        self.false_alarm_counts = np.zeros(B, dtype=np.int64)
        self.last_visit_slot = np.full(B, -1, dtype=np.int64)
        self.predicted_activity = np.full(B, 0.1, dtype=np.float64)
        self.band_threat_prior = self.env.band_threat_prior()
        self.reward_history: list[float] = []
        self._last_feedback: ScanFeedback | None = None

    # ------------------------------------------------------------------ #
    @property
    def max_slots(self) -> int:
        return self.env.num_time_slots

    def _context(self) -> SchedulerContext:
        return SchedulerContext(
            time_slot=self.t,
            num_bands=self.env.num_bands,
            current_band=self.receiver.state.current_band,
            retune_delay=self.receiver_config.retune_delay_slots,
            visit_counts=self.visit_counts,
            hit_counts=self.hit_counts,
            miss_counts=self.miss_counts,
            false_alarm_counts=self.false_alarm_counts,
            last_visit_slot=self.last_visit_slot,
            predicted_activity=self.predicted_activity,
            band_threat_prior=self.band_threat_prior,
            recent_reward=self.reward_history[-1] if self.reward_history else 0.0,
            last_feedback=self._last_feedback,
        )

    # ------------------------------------------------------------------ #
    def step(self) -> SimulationStepResult:
        if self.done:
            raise RuntimeError("Simulation finished; reset to run again.")

        t = self.t
        decision: ScanDecision = self.scheduler.decide(self._context())
        band = int(np.clip(decision.selected_band, 0, self.env.num_bands - 1))

        retuned = self.receiver.tune(band)
        measurement = self.receiver.observe(self.env, t, band)

        true_active = measurement["true_active"]
        detected = measurement["detected"]
        false_alarm = measurement["false_alarm"]
        threat = measurement["threat"]

        # Missed-opportunity context for the reward engine.
        missed_bands = 0
        missed_hp = 0
        for b in self.env.active_bands(t):
            if b == band:
                continue
            missed_bands += 1
            if self.env.threat_at(t, b) >= HIGH_PRIORITY_THREAT:
                missed_hp += 1

        reward, breakdown = compute_reward(
            true_active=true_active,
            detected=detected,
            false_alarm=false_alarm,
            threat=threat,
            retuned=retuned,
            predicted_active=decision.predicted_active,
            missed_active_bands=missed_bands,
            missed_high_priority_bands=missed_hp,
        )

        # --- update running estimates -------------------------------- #
        self.visit_counts[band] += 1
        self.last_visit_slot[band] = t
        if true_active and detected:
            self.hit_counts[band] += 1
        elif true_active and not detected:
            self.miss_counts[band] += 1
        if false_alarm:
            self.false_alarm_counts[band] += 1

        obs = 1.0 if (true_active and detected) else 0.0
        alpha = 0.2
        self.predicted_activity[band] = (
            (1 - alpha) * self.predicted_activity[band] + alpha * obs
        )

        self.reward_history.append(reward)

        feedback = ScanFeedback(
            time_slot=t,
            band=band,
            true_active=true_active,
            detected=detected,
            false_alarm=false_alarm,
            reward=reward,
            reward_breakdown=breakdown,
            predicted_active=decision.predicted_active,
        )
        self.scheduler.update(feedback)
        self._last_feedback = feedback

        self.metrics.record(
            t=t,
            scanned_band=band,
            true_active=true_active,
            detected=detected,
            false_alarm=false_alarm,
            predicted_active=decision.predicted_active,
            reward=reward,
            env=self.env,
        )

        detection_event = DetectionEvent(
            time_slot=t,
            band=measurement["band"],
            true_active=true_active,
            detected=detected,
            false_alarm=false_alarm,
            measured_snr_db=measurement["measured_snr_db"],
            measured_power_db=measurement["measured_power_db"],
            threat=threat,
        )

        # Advance time by the dwell length.
        self.t += max(1, self.receiver_config.dwell_slots)
        self.done = self.t >= self.max_slots

        result = SimulationStepResult(
            time_slot=t,
            decision=decision,
            detection=detection_event,
            reward=round(reward, 3),
            reward_breakdown={k: round(v, 3) for k, v in breakdown.items()},
            retuned=retuned,
            done=self.done,
            metrics=self.metrics.snapshot(up_to_t=t),
        )
        self.history.append(result)
        return result

    def run(self, steps: int) -> list[SimulationStepResult]:
        out: list[SimulationStepResult] = []
        for _ in range(steps):
            if self.done:
                break
            out.append(self.step())
        return out

    # ------------------------------------------------------------------ #
    def metrics_snapshot(self) -> SchedulerMetrics:
        last_t = self.history[-1].time_slot if self.history else 0
        return self.metrics.snapshot(up_to_t=last_t)
