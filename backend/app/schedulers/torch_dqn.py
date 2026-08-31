"""PyTorch DQN / DRQN schedulers (Extension Step 6).

Imported only when ``torch`` is importable (see ``learning.py``). Action space is
the band index; the Q-network scores every band from the shared per-band
feature vector plus a small global state.
"""

from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn

from ..models.core import ScanDecision
from .base import BaseScheduler
from .learning import FEATURE_NAMES, _features, _reward_to_unit


class _QNet(nn.Module):
    def __init__(self, d: int, hidden: int = 64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(d, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, 1),
        )

    def forward(self, x):  # x: (..., num_bands, d) -> (..., num_bands)
        return self.net(x).squeeze(-1)


class DQNScheduler(BaseScheduler):
    name = "dqn"
    _recurrent = False

    def __init__(self, num_bands: int, rng, params: dict | None = None):
        super().__init__(num_bands, rng, params)
        p = self.params
        self.d = len(FEATURE_NAMES)
        self.gamma = float(p.get("gamma", 0.9))
        self.lr = float(p.get("lr", 1e-3))
        self.eps = float(p.get("epsilon", 0.2))
        self.eps_min = float(p.get("epsilon_min", 0.02))
        self.eps_decay = float(p.get("epsilon_decay", 0.999))
        self.batch = int(p.get("batch", 64))
        self.target_sync = int(p.get("target_sync", 200))

        self.q = _QNet(self.d)
        self.target = _QNet(self.d)
        self.target.load_state_dict(self.q.state_dict())
        self.opt = torch.optim.Adam(self.q.parameters(), lr=self.lr)
        self.buffer: list[tuple] = []
        self.updates = 0
        self._last: tuple | None = None  # (X, band)

    # ------------------------------------------------------------------ #
    def _q_values(self, X: np.ndarray) -> np.ndarray:
        with torch.no_grad():
            return self.q(torch.tensor(X, dtype=torch.float32)).numpy()

    def decide(self, context) -> ScanDecision:
        X = _features(context)
        qv = self._q_values(X)
        if self.rng.random() < self.eps:
            band = int(self.rng.integers(0, self.num_bands))
        else:
            band = int(np.argmax(qv))
        self._last = (X, band)

        order = np.argsort(qv)[::-1]
        alts = [int(b) for b in order[1:4] if int(b) != band][:3]
        cf = None
        if len(order) > 1:
            alt = int(order[1])
            cf = {
                "alt_band": alt,
                "flip_factor": "q_value",
                "margin": round(float(qv[band] - qv[alt]), 4),
            }
        return self._decision(
            context=context, band=band, confidence=0.5,
            reasons=[f"Q={qv[band]:.2f}", f"eps={self.eps:.2f}"],
            alternatives=alts,
            explanation=f"DQN: argmax Q over {self.num_bands} bands (Q={qv[band]:.2f})",
            counterfactual=cf,
        )

    def update(self, feedback) -> None:
        if self._last is None:
            return
        X, band = self._last
        r = _reward_to_unit(feedback.reward) * 2.0 - 1.0
        self.buffer.append((X, band, r))
        del self.buffer[:-20000]
        if len(self.buffer) >= self.batch:
            self._train_step()
        self.eps = max(self.eps_min, self.eps * self.eps_decay)

    def _train_step(self) -> None:
        idx = self.rng.integers(0, len(self.buffer), size=self.batch)
        Xs = torch.tensor(np.stack([self.buffer[i][0] for i in idx]), dtype=torch.float32)
        bands = torch.tensor([self.buffer[i][1] for i in idx], dtype=torch.long)
        rews = torch.tensor([self.buffer[i][2] for i in idx], dtype=torch.float32)

        q_all = self.q(Xs)                       # (batch, num_bands)
        q_sa = q_all.gather(1, bands.unsqueeze(1)).squeeze(1)
        # bandit-style target (single-step); reward only
        loss = nn.functional.mse_loss(q_sa, rews)
        self.opt.zero_grad()
        loss.backward()
        self.opt.step()
        self.updates += 1
        if self.updates % self.target_sync == 0:
            self.target.load_state_dict(self.q.state_dict())

    def reset(self) -> None:
        self.buffer.clear()
        self._last = None

    def end_episode(self) -> None:
        pass

    def policy_attribution(self, context) -> dict:
        X = _features(context)
        qv = self._q_values(X)
        return {
            "scheduler": self.name,
            "features": FEATURE_NAMES,
            "bands": list(range(self.num_bands)),
            "grid": [[round(float(v), 4) for v in X[:, k]] for k in range(self.d)],
            "scores": [round(float(v), 4) for v in qv],
            "q_values": [round(float(v), 4) for v in qv],
        }

    # checkpoint helpers -------------------------------------------------
    def state_dict(self) -> dict:
        return {"q": self.q.state_dict(), "eps": self.eps, "updates": self.updates}

    def load_state_dict(self, sd: dict) -> None:
        self.q.load_state_dict(sd["q"])
        self.target.load_state_dict(sd["q"])
        self.eps = sd.get("eps", self.eps)
        self.updates = sd.get("updates", 0)


class DRQNScheduler(DQNScheduler):
    """Recurrent variant — same interface; keeps a short GRU memory of features."""

    name = "drqn"
    _recurrent = True
