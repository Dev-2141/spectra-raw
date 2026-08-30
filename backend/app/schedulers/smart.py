"""Adaptive schedulers: priority score + multi-armed bandits.

All of these obey the information boundary in :mod:`app.schedulers.base` — they
see only visit / hit / miss / false-alarm history, running activity estimates,
static threat priors, and reward feedback. Never the ground-truth occupancy.
"""

from __future__ import annotations

import numpy as np

from ..models.core import ScanDecision
from .base import BaseScheduler


def _confidence(scores: np.ndarray, idx: int) -> float:
    lo, hi = float(scores.min()), float(scores.max())
    if hi - lo < 1e-9:
        return 1.0 / len(scores)
    return float((scores[idx] - lo) / (hi - lo))


def _reward_to_unit(reward: float) -> float:
    """Squash the spec reward (~[-10, 10]) into [0, 1] for bounded bandit values."""
    return float(np.clip((reward + 10.0) / 20.0, 0.0, 1.0))


# --------------------------------------------------------------------------- #
# 1. Priority score
# --------------------------------------------------------------------------- #
class PriorityScoreScheduler(BaseScheduler):
    """Weighted score over recent activity, staleness, uncertainty, threat,
    periodicity estimate, and previous hit rate."""

    name = "priority"

    _DEFAULT_WEIGHTS = {
        "activity": 1.0,
        "staleness": 0.8,
        "uncertainty": 0.4,
        "threat": 1.2,
        "hit_rate": 0.7,
        "periodicity": 1.0,
    }

    def __init__(self, num_bands: int, rng, params: dict | None = None):
        super().__init__(num_bands, rng, params)
        w = dict(self._DEFAULT_WEIGHTS)
        w.update(self.params.get("weights", {}))
        self.w = w
        self.tiebreak = float(self.params.get("tiebreak_noise", 0.01))
        self._hit_slots: dict[int, list[int]] = {b: [] for b in range(num_bands)}
        self._period_est = np.zeros(num_bands, dtype=np.float64)
        self._last_components: dict | None = None

    def reset(self) -> None:
        self._hit_slots = {b: [] for b in range(self.num_bands)}
        self._period_est[:] = 0.0
        self._last_components = None

    # ------------------------------------------------------------------ #
    def _periodicity_bonus(self, band: int, since: int) -> float:
        p = self._period_est[band]
        if p <= 1.0 or since < 0:
            return 0.0
        phase_frac = (since % p) / p
        dist = min(phase_frac, 1.0 - phase_frac)
        return float(np.exp(-((dist / 0.15) ** 2)))

    def decide(self, context) -> ScanDecision:
        B = self.num_bands
        t = context.time_slot
        visits = context.visit_counts.astype(np.float64)
        last_visit = context.last_visit_slot

        since = np.where(last_visit < 0, t + B, t - last_visit).astype(np.float64)
        activity = context.predicted_activity.astype(np.float64)
        staleness = np.clip(since / (2.0 * B), 0.0, 1.0)
        uncertainty = 1.0 / np.sqrt(visits + 1.0)
        threat = context.band_threat_prior.astype(np.float64)
        hit_rate = context.hit_counts / np.maximum(1.0, visits)
        periodicity = np.array(
            [self._periodicity_bonus(b, int(since[b])) for b in range(B)]
        )

        w = self.w
        contrib = {
            "activity": w["activity"] * activity,
            "staleness": w["staleness"] * staleness,
            "uncertainty": w["uncertainty"] * uncertainty,
            "threat": w["threat"] * threat,
            "hit_rate": w["hit_rate"] * hit_rate,
            "periodicity": w["periodicity"] * periodicity,
        }
        score = sum(contrib.values())
        score = score + self.rng.normal(0.0, self.tiebreak, size=B)

        band = int(np.argmax(score))
        order = np.argsort(score)[::-1]
        alternatives = [int(b) for b in order[1:4] if int(b) != band][:3]

        parts = sorted(
            ((k, float(v[band])) for k, v in contrib.items()),
            key=lambda kv: kv[1],
            reverse=True,
        )
        top = [f"{k} ({v:.2f})" for k, v in parts[:3]]

        v = int(context.visit_counts[band])
        act = float(activity[band])
        if act >= 0.5 or (periodicity[band] >= 0.6 and context.hit_counts[band] > 0):
            predicted_active: bool | None = True
        elif v >= 3 and act <= 0.1:
            predicted_active = False
        else:
            predicted_active = None

        p_est = self._period_est[band]
        expl = (
            f"Band {band}: threat {threat[band]:.2f}, activity est {act:.2f}, "
            f"{int(since[band])} slots since last visit"
        )
        if p_est > 1:
            expl += f", est. period ~{p_est:.0f}"

        return self._decision(
            context=context,
            band=band,
            confidence=_confidence(score, band),
            predicted_active=predicted_active,
            reasons=top,
            alternatives=alternatives,
            explanation=expl,
        )

    def update(self, feedback) -> None:
        b = feedback.band
        if feedback.detected and feedback.true_active:
            slots = self._hit_slots.setdefault(b, [])
            slots.append(feedback.time_slot)
            if len(slots) > 12:
                del slots[0]
            if len(slots) >= 3:
                gaps = np.diff(slots)
                gaps = gaps[gaps > 0]
                if len(gaps) >= 2 and gaps.std() <= 0.5 * gaps.mean() + 1.0:
                    self._period_est[b] = float(np.median(gaps))


# --------------------------------------------------------------------------- #
# Shared bandit base
# --------------------------------------------------------------------------- #
class _BanditBase(BaseScheduler):
    def __init__(self, num_bands: int, rng, params: dict | None = None):
        super().__init__(num_bands, rng, params)
        self.values = np.full(
            num_bands, float(self.params.get("optimistic_init", 0.5)), dtype=np.float64
        )
        self.counts = np.zeros(num_bands, dtype=np.int64)
        self.hit_est = np.full(num_bands, 0.1, dtype=np.float64)

    def reset(self) -> None:
        self.values[:] = float(self.params.get("optimistic_init", 0.5))
        self.counts[:] = 0
        self.hit_est[:] = 0.1

    def _predicted_active(self, band: int) -> bool | None:
        if self.hit_est[band] >= 0.5:
            return True
        if self.counts[band] >= 3 and self.hit_est[band] <= 0.1:
            return False
        return None

    def update(self, feedback) -> None:
        b = feedback.band
        self.counts[b] += 1
        payoff = _reward_to_unit(feedback.reward)
        self.values[b] += (payoff - self.values[b]) / self.counts[b]
        hit = 1.0 if (feedback.detected and feedback.true_active) else 0.0
        n = self.counts[b]
        self.hit_est[b] += (hit - self.hit_est[b]) / n


# --------------------------------------------------------------------------- #
# 2. Epsilon-greedy bandit
# --------------------------------------------------------------------------- #
class EpsilonGreedyBanditScheduler(_BanditBase):
    """Each band is an arm; explore with probability epsilon, else exploit."""

    name = "epsilon_bandit"

    def __init__(self, num_bands: int, rng, params: dict | None = None):
        super().__init__(num_bands, rng, params)
        self.epsilon = float(self.params.get("epsilon", 0.1))
        self.epsilon_min = float(self.params.get("epsilon_min", 0.02))
        self.epsilon_decay = float(self.params.get("epsilon_decay", 1.0))

    def reset(self) -> None:
        super().reset()
        self.epsilon = float(self.params.get("epsilon", 0.1))

    def decide(self, context) -> ScanDecision:
        explore = self.rng.random() < self.epsilon
        if explore:
            band = int(self.rng.integers(0, self.num_bands))
            reasons = [
                f"exploration (epsilon={self.epsilon:.3f})",
                "random arm pull",
                f"arm pulled {int(self.counts[band])}x so far",
            ]
            conf = self.epsilon
        else:
            band = int(np.argmax(self.values))
            reasons = [
                f"exploit best arm (value={self.values[band]:.3f})",
                f"pulled {int(self.counts[band])}x",
                f"hit-rate est {self.hit_est[band]:.2f}",
            ]
            conf = _confidence(self.values, band)

        order = np.argsort(self.values)[::-1]
        alts = [int(b) for b in order[:4] if int(b) != band][:3]
        return self._decision(
            context=context,
            band=band,
            confidence=conf,
            predicted_active=self._predicted_active(band),
            reasons=reasons,
            alternatives=alts,
            explanation=(
                f"{'Explore' if explore else 'Exploit'} band {band}; "
                f"value {self.values[band]:.3f}, pulls {int(self.counts[band])}."
            ),
        )

    def update(self, feedback) -> None:
        super().update(feedback)
        if self.epsilon_decay < 1.0:
            self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)


# --------------------------------------------------------------------------- #
# 3. UCB1 bandit
# --------------------------------------------------------------------------- #
class UCB1BanditScheduler(_BanditBase):
    """Upper-confidence-bound arm selection; unpulled arms get priority."""

    name = "ucb_bandit"

    def __init__(self, num_bands: int, rng, params: dict | None = None):
        super().__init__(num_bands, rng, params)
        self.c = float(self.params.get("c", 2.0))
        self._total = 0

    def reset(self) -> None:
        super().reset()
        self._total = 0

    def decide(self, context) -> ScanDecision:
        self._total += 1
        t = self._total

        unpulled = np.nonzero(self.counts == 0)[0]
        if len(unpulled) > 0:
            band = int(unpulled[0])
            bonus = float("inf")
            ucb = self.values.copy()
            reasons = [
                "under-scanned arm (0 pulls)",
                "confidence bonus = infinite",
                f"{len(unpulled)} arms still unpulled",
            ]
            conf = 0.2
        else:
            bonus_vec = self.c * np.sqrt(np.log(t) / self.counts)
            ucb = self.values + bonus_vec
            band = int(np.argmax(ucb))
            bonus = float(bonus_vec[band])
            reasons = [
                f"UCB {ucb[band]:.3f} = value {self.values[band]:.3f} + bonus {bonus:.3f}",
                f"pulled {int(self.counts[band])}x of {t}",
                f"hit-rate est {self.hit_est[band]:.2f}",
            ]
            conf = _confidence(ucb, band)

        order = np.argsort(ucb)[::-1]
        alts = [int(b) for b in order[:4] if int(b) != band][:3]
        return self._decision(
            context=context,
            band=band,
            confidence=conf,
            predicted_active=self._predicted_active(band),
            reasons=reasons,
            alternatives=alts,
            explanation=(
                f"UCB1 selects band {band}: exploit value {self.values[band]:.3f}, "
                f"exploration bonus {bonus if bonus != float('inf') else 'inf'}."
            ),
        )


# --------------------------------------------------------------------------- #
# 4. Thompson sampling (Beta-Bernoulli on detection)
# --------------------------------------------------------------------------- #
class ThompsonSamplingScheduler(BaseScheduler):
    """Beta posterior per band on P(hit); sample and pick the max draw."""

    name = "thompson"

    def __init__(self, num_bands: int, rng, params: dict | None = None):
        super().__init__(num_bands, rng, params)
        a0 = float(self.params.get("alpha_prior", 1.0))
        b0 = float(self.params.get("beta_prior", 1.0))
        self.alpha = np.full(num_bands, a0, dtype=np.float64)
        self.beta = np.full(num_bands, b0, dtype=np.float64)

    def reset(self) -> None:
        a0 = float(self.params.get("alpha_prior", 1.0))
        b0 = float(self.params.get("beta_prior", 1.0))
        self.alpha[:] = a0
        self.beta[:] = b0

    def decide(self, context) -> ScanDecision:
        samples = self.rng.beta(self.alpha, self.beta)
        band = int(np.argmax(samples))
        mean = self.alpha / (self.alpha + self.beta)

        order = np.argsort(samples)[::-1]
        alts = [int(b) for b in order[:4] if int(b) != band][:3]

        pm = float(mean[band])
        predicted_active = True if pm >= 0.5 else (False if pm <= 0.1 else None)
        return self._decision(
            context=context,
            band=band,
            confidence=_confidence(samples, band),
            predicted_active=predicted_active,
            reasons=[
                f"sampled theta={samples[band]:.3f}",
                f"posterior mean {pm:.3f} (a={self.alpha[band]:.1f}, b={self.beta[band]:.1f})",
                "highest Beta draw this slot",
            ],
            alternatives=alts,
            explanation=(
                f"Thompson sampling: band {band} drew the top posterior sample "
                f"({samples[band]:.3f}); posterior mean P(hit) {pm:.3f}."
            ),
        )

    def update(self, feedback) -> None:
        b = feedback.band
        if feedback.detected and feedback.true_active:
            self.alpha[b] += 1.0
        else:
            self.beta[b] += 1.0
        if feedback.false_alarm:
            self.beta[b] += 1.0
