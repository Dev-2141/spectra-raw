"""Reward engine.

Turns a single scan outcome (plus the missed-opportunity context) into a scalar
reward and a human-readable breakdown. Values follow the project spec:

    +10 high-priority detection      -2  empty scan
    +5  normal detection             -4  false alarm
    +1  correct inactive prediction  -6  missed active signal
    -1  retune / dwell cost          -10 missed high-priority signal

Step 2 extends this with per-scheduler shaping; the core table stays fixed.
"""

from __future__ import annotations

HIGH_PRIORITY_THREAT = 0.7

R_HIGH_PRIORITY_DETECT = 10.0
R_NORMAL_DETECT = 5.0
R_CORRECT_INACTIVE = 1.0
R_EMPTY_SCAN = -2.0
R_FALSE_ALARM = -4.0
R_MISSED_ACTIVE = -6.0
R_MISSED_HIGH_PRIORITY = -10.0
R_RETUNE_COST = -1.0
R_DWELL_COST = -0.0  # dwell cost folded into retune for now


def compute_reward(
    *,
    true_active: bool,
    detected: bool,
    false_alarm: bool,
    threat: float,
    retuned: bool,
    predicted_active: bool | None,
    missed_active_bands: int = 0,
    missed_high_priority_bands: int = 0,
) -> tuple[float, dict]:
    """Return ``(reward, breakdown)`` for one dwell."""
    breakdown: dict[str, float] = {}
    high_priority = threat >= HIGH_PRIORITY_THREAT

    if true_active and detected:
        if high_priority:
            breakdown["high_priority_detection"] = R_HIGH_PRIORITY_DETECT
        else:
            breakdown["detection"] = R_NORMAL_DETECT
    elif true_active and not detected:
        # Scanned the right band but the estimator missed it.
        breakdown["detection_miss"] = R_MISSED_HIGH_PRIORITY if high_priority else R_MISSED_ACTIVE

    if false_alarm:
        breakdown["false_alarm"] = R_FALSE_ALARM

    if not true_active and not false_alarm:
        if predicted_active is False:
            breakdown["correct_inactive"] = R_CORRECT_INACTIVE
        else:
            breakdown["empty_scan"] = R_EMPTY_SCAN

    if retuned:
        breakdown["retune_cost"] = R_RETUNE_COST

    if missed_active_bands > 0:
        normal_missed = max(0, missed_active_bands - missed_high_priority_bands)
        if normal_missed:
            breakdown["missed_active"] = R_MISSED_ACTIVE * normal_missed
        if missed_high_priority_bands:
            breakdown["missed_high_priority"] = (
                R_MISSED_HIGH_PRIORITY * missed_high_priority_bands
            )

    reward = float(sum(breakdown.values()))
    return reward, breakdown


class RewardEngine:
    """OO wrapper around :func:`compute_reward`.

    Consumes the ground-truth activity flag, the scheduler decision, the
    detection event, and the missed-opportunity context, and returns a scalar
    reward plus a per-component breakdown for the explainability log.
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def evaluate(
        self,
        *,
        true_active: bool,
        detected: bool,
        false_alarm: bool,
        threat: float,
        retuned: bool,
        predicted_active: bool | None,
        missed_active_bands: int = 0,
        missed_high_priority_bands: int = 0,
    ) -> tuple[float, dict]:
        return compute_reward(
            true_active=true_active,
            detected=detected,
            false_alarm=false_alarm,
            threat=threat,
            retuned=retuned,
            predicted_active=predicted_active,
            missed_active_bands=missed_active_bands,
            missed_high_priority_bands=missed_high_priority_bands,
        )
