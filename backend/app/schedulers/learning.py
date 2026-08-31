"""Learning-based schedulers (Extension Step 6).

- ``contextual_bandit`` — LinUCB over a per-band feature vector. Pure NumPy.
- ``dqn`` / ``drqn`` — PyTorch, lazy-imported and flag-gated. If torch is not
  installed, selecting them raises a clear error and nothing else breaks.
"""

from __future__ import annotations

import numpy as np

from ..models.core import ScanDecision
from .base import BaseScheduler

FEATURE_NAMES = [
    "activity",
    "staleness",
    "uncertainty",
    "threat",
    "hit_rate",
    "tasking",
    "bias",
]


def _features(context) -> np.ndarray:
    """(num_bands, d) feature matrix from the compact scheduler context."""
    B = context.num_bands
    t = context.time_slot
    visits = context.visit_counts.astype(np.float64)
    last_visit = context.last_visit_slot
    since = np.where(last_visit < 0, t + B, t - last_visit).astype(np.float64)

    activity = context.predicted_activity.astype(np.float64)
    staleness = np.clip(since / (2.0 * B), 0.0, 1.0)
    uncertainty = 1.0 / np.sqrt(visits + 1.0)
    threat = context.band_threat_prior.astype(np.float64)
    hit_rate = context.hit_counts / np.maximum(1.0, visits)

    tw = getattr(context, "tasking_weights", None)
    tasking = (np.asarray(tw, dtype=np.float64) - 1.0) if tw is not None else np.zeros(B)

    return np.column_stack(
        [activity, staleness, uncertainty, threat, hit_rate, tasking, np.ones(B)]
    )


def _reward_to_unit(reward: float) -> float:
    return float(np.clip((reward + 10.0) / 20.0, 0.0, 1.0))


# --------------------------------------------------------------------------- #
class ContextualBanditScheduler(BaseScheduler):
    """LinUCB: one ridge-regression arm per band over the shared feature vector."""

    name = "contextual_bandit"

    def __init__(self, num_bands: int, rng, params: dict | None = None):
        super().__init__(num_bands, rng, params)
        self.d = len(FEATURE_NAMES)
        self.alpha = float(self.params.get("alpha", 0.6))
        self.lam = float(self.params.get("ridge", 1.0))
        self._reset_arms()
        self._last_x: np.ndarray | None = None
        self._last_band: int | None = None

    def _reset_arms(self) -> None:
        self.A = np.stack([self.lam * np.eye(self.d) for _ in range(self.num_bands)])
        self.b = np.zeros((self.num_bands, self.d))

    def reset(self) -> None:
        self._reset_arms()
        self._last_x = None
        self._last_band = None

    # ------------------------------------------------------------------ #
    def _scores(self, X: np.ndarray):
        mu = np.zeros(self.num_bands)
        bonus = np.zeros(self.num_bands)
        theta = np.zeros((self.num_bands, self.d))
        for i in range(self.num_bands):
            Ainv = np.linalg.inv(self.A[i])
            th = Ainv @ self.b[i]
            theta[i] = th
            x = X[i]
            mu[i] = float(th @ x)
            bonus[i] = self.alpha * float(np.sqrt(max(x @ Ainv @ x, 0.0)))
        return mu, bonus, theta

    def decide(self, context) -> ScanDecision:
        X = _features(context)
        mu, bonus, theta = self._scores(X)
        p = mu + bonus
        p = p + self.rng.normal(0.0, 1e-4, size=self.num_bands)

        order = np.argsort(p)[::-1]
        band = int(order[0])
        alts = [int(b) for b in order[1:4]]
        self._last_x = X[band].copy()
        self._last_band = band

        cf = None
        if len(order) > 1:
            alt = int(order[1])
            contrib_sel = theta[band] * X[band]
            contrib_alt = theta[alt] * X[alt]
            k = int(np.argmax(contrib_sel - contrib_alt))
            cf = {
                "alt_band": alt,
                "flip_factor": FEATURE_NAMES[k],
                "margin": round(float(p[band] - p[alt]), 4),
            }

        conf = float(np.clip((p[band] - p[order[-1]]) / (abs(p[band]) + 1e-6), 0.0, 1.0))
        top = sorted(
            zip(FEATURE_NAMES, (theta[band] * X[band]).tolist()),
            key=lambda kv: kv[1],
            reverse=True,
        )
        reasons = [f"{k} ({v:+.2f})" for k, v in top[:3]]
        expl = (
            f"Band {band}: LinUCB score {p[band]:.2f} "
            f"(mean {mu[band]:.2f} + explore {bonus[band]:.2f})"
        )
        return self._decision(
            context=context,
            band=band,
            confidence=conf,
            predicted_active=True if mu[band] > 0.5 else (False if mu[band] < 0.1 else None),
            reasons=reasons,
            alternatives=alts,
            explanation=expl,
            counterfactual=cf,
        )

    def update(self, feedback) -> None:
        if self._last_x is None or self._last_band is None:
            return
        # Attribute the outcome to the arm we chose, with the features we scored.
        band = self._last_band
        x = self._last_x
        r = _reward_to_unit(feedback.reward)
        self.A[band] += np.outer(x, x)
        self.b[band] += r * x

    def policy_attribution(self, context) -> dict:
        X = _features(context)
        mu, bonus, theta = self._scores(X)
        grid = (theta * X).T  # (d, num_bands)
        return {
            "scheduler": self.name,
            "features": FEATURE_NAMES,
            "bands": list(range(self.num_bands)),
            "grid": [[round(float(v), 4) for v in row] for row in grid],
            "scores": [round(float(v), 4) for v in (mu + bonus)],
        }

    # checkpoint helpers ------------------------------------------------- #
    def state_dict(self) -> dict:
        return {
            "kind": "contextual_bandit",
            "num_bands": self.num_bands,
            "alpha": self.alpha,
            "lam": self.lam,
            "A": self.A.tolist(),
            "b": self.b.tolist(),
        }

    def load_state_dict(self, sd: dict) -> None:
        if int(sd.get("num_bands", self.num_bands)) != self.num_bands:
            return
        self.alpha = float(sd.get("alpha", self.alpha))
        self.lam = float(sd.get("lam", self.lam))
        self.A = np.array(sd["A"], dtype=np.float64)
        self.b = np.array(sd["b"], dtype=np.float64)


# --------------------------------------------------------------------------- #
# Torch-gated DQN / DRQN
# --------------------------------------------------------------------------- #
def torch_available() -> bool:
    try:
        import torch  # noqa: F401

        return True
    except Exception:
        return False


class _TorchRequired(BaseScheduler):
    """Placeholder so the registry lists the name; constructing it explains why."""

    name = "dqn"

    def __init__(self, num_bands: int, rng, params: dict | None = None):
        raise ValueError(
            f"scheduler '{self.name}' requires PyTorch. Install it "
            "(`pip install torch`) and set FLAG_TORCH_RL=1, or use "
            "'contextual_bandit' / 'priority'."
        )

    def decide(self, context) -> ScanDecision:  # pragma: no cover
        raise RuntimeError("torch required")


class _DQNRequired(_TorchRequired):
    name = "dqn"


class _DRQNRequired(_TorchRequired):
    name = "drqn"


if torch_available():  # pragma: no cover - exercised only with torch installed
    from .torch_dqn import DQNScheduler, DRQNScheduler
else:
    DQNScheduler = _DQNRequired
    DRQNScheduler = _DRQNRequired
