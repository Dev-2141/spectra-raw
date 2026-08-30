"""Incremental metrics tracker.

Consumes per-step outcomes and the environment's event list to produce the
:class:`SchedulerMetrics` payload. Nothing here is hardcoded to a strategy.
"""

from __future__ import annotations

from collections import defaultdict

from ..models.core import SchedulerMetrics
from ..simulation.environment import RFEnvironment
from ..simulation.reward import HIGH_PRIORITY_THREAT


class MetricsTracker:
    def __init__(self, env: RFEnvironment):
        self.env = env
        self.num_bands = env.num_bands

        self.steps = 0
        self.total_reward = 0.0

        self.hits = 0                 # scanned an active band and detected it
        self.misses = 0              # scanned an active band, no detection
        self.false_alarms = 0
        self.empty_scans = 0         # scanned inactive band, no false alarm

        self.active_scans = 0        # scans that landed on a truly active band
        self.inactive_scans = 0

        self.predictions = 0
        self.correct_predictions = 0

        self.missed_opportunities = 0

        self.visit_slots: dict[int, list[int]] = defaultdict(list)
        self.visited: set[int] = set()

        # Event interception bookkeeping (keyed by identity in env.events).
        self._events = env.events
        self._event_lookup: dict[tuple[int, int], list] = defaultdict(list)
        for e in self._events:
            self._event_lookup[e.band].append(e)

    # ------------------------------------------------------------------ #
    def record(
        self,
        *,
        t: int,
        scanned_band: int,
        true_active: bool,
        detected: bool,
        false_alarm: bool,
        predicted_active: bool | None,
        reward: float,
        env: RFEnvironment,
    ) -> None:
        self.steps += 1
        self.total_reward += reward

        self.visited.add(scanned_band)
        self.visit_slots[scanned_band].append(t)

        if true_active:
            self.active_scans += 1
            if detected:
                self.hits += 1
                self._mark_event_detected(scanned_band, t)
            else:
                self.misses += 1
        else:
            self.inactive_scans += 1
            if false_alarm:
                self.false_alarms += 1
            else:
                self.empty_scans += 1

        if predicted_active is not None:
            self.predictions += 1
            if predicted_active == true_active:
                self.correct_predictions += 1

        # Missed opportunities: active bands this slot that we did not scan.
        for b in env.active_bands(t):
            if b != scanned_band:
                self.missed_opportunities += 1

    def _mark_event_detected(self, band: int, t: int) -> None:
        for e in self._event_lookup.get(band, ()):
            if e.start <= t <= e.end and not e.detected:
                e.detected = True
                e.first_detection_slot = t
                return

    # ------------------------------------------------------------------ #
    def snapshot(self, up_to_t: int) -> SchedulerMetrics:
        events_so_far = [e for e in self._events if e.start <= up_to_t]
        detected_events = [e for e in events_so_far if e.detected]
        hp_events = [e for e in events_so_far if e.high_priority or e.threat >= HIGH_PRIORITY_THREAT]
        hp_detected = [e for e in hp_events if e.detected]

        delays = [
            (e.first_detection_slot - e.start)
            for e in detected_events
            if e.first_detection_slot is not None
        ]

        revisit_gaps: list[int] = []
        for slots in self.visit_slots.values():
            if len(slots) >= 2:
                revisit_gaps.extend(
                    b - a for a, b in zip(slots, slots[1:])
                )

        pod = self.hits / self.active_scans if self.active_scans else 0.0
        far = self.false_alarms / self.inactive_scans if self.inactive_scans else 0.0
        interception = (
            len(detected_events) / len(events_so_far) if events_so_far else 0.0
        )
        avg_delay = sum(delays) / len(delays) if delays else 0.0
        hp_rate = len(hp_detected) / len(hp_events) if hp_events else 0.0
        coverage = len(self.visited) / self.num_bands if self.num_bands else 0.0
        avg_revisit = sum(revisit_gaps) / len(revisit_gaps) if revisit_gaps else 0.0
        correct_pct = (
            100.0 * self.correct_predictions / self.predictions
            if self.predictions
            else 0.0
        )
        avg_reward = self.total_reward / self.steps if self.steps else 0.0

        return SchedulerMetrics(
            steps=self.steps,
            total_reward=round(self.total_reward, 3),
            average_reward=round(avg_reward, 4),
            hits=self.hits,
            misses=self.misses,
            false_alarms=self.false_alarms,
            empty_scans=self.empty_scans,
            probability_of_detection=round(pod, 4),
            false_alarm_rate=round(far, 4),
            interception_ratio=round(interception, 4),
            average_intercept_delay=round(avg_delay, 3),
            high_priority_detection_rate=round(hp_rate, 4),
            missed_opportunity_count=self.missed_opportunities,
            scan_coverage=round(coverage, 4),
            average_revisit_time=round(avg_revisit, 3),
            correct_prediction_percentage=round(correct_pct, 2),
            emitter_events_total=len(events_so_far),
            emitter_events_detected=len(detected_events),
        )
