"""Online adaptation guardrail (Extension Step 6).

In live mode a learning scheduler may keep updating from the *proxy* reward
(no ground-truth claim). A shadow ``priority`` decision is scored each step; if
the online policy's rolling proxy reward falls below the shadow by ``margin``
for a sustained window, the platform auto-reverts to ``priority`` and raises an
alert. All transitions are audited by the caller.
"""

from __future__ import annotations

import threading

import numpy as np

from ..models.core import OnlineStatus


class OnlineGuardrail:
    def __init__(self, margin: float = 1.5, window: int = 80) -> None:
        self.margin = float(margin)
        self.window = int(window)
        self._alpha = 2.0 / (self.window + 1.0)
        self.policy_ema = 0.0
        self.shadow_ema = 0.0
        self.breaches = 0
        self.updates = 0
        self.reverted = False
        self.reverted_at_slot: int | None = None
        self._seen = 0

    def observe(self, time_slot: int, policy_reward: float, shadow_reward: float) -> str | None:
        if self.reverted:
            # inert once tripped — EMAs freeze at the moment of revert
            return None
        self.updates += 1
        self._seen += 1
        self.policy_ema += self._alpha * (policy_reward - self.policy_ema)
        self.shadow_ema += self._alpha * (shadow_reward - self.shadow_ema)
        # need at least a partial window before judging
        if self._seen < max(10, self.window // 2):
            return None
        if self.policy_ema < self.shadow_ema - self.margin:
            self.breaches += 1
        else:
            self.breaches = max(0, self.breaches - 2)
        if self.breaches >= max(5, self.window // 4):
            self.reverted = True
            self.reverted_at_slot = int(time_slot)
            return "revert"
        return None


class OnlineManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.enabled = False
        self.active_scheduler = ""
        self.guardrail: OnlineGuardrail | None = None
        self._shadow = None

    def enable(self, scheduler: str, margin: float, window: int) -> OnlineStatus:
        from ..schedulers.registry import create_scheduler

        with self._lock:
            self.enabled = True
            self.active_scheduler = scheduler
            self.guardrail = OnlineGuardrail(margin, window)
            self._shadow = create_scheduler(
                "priority", 8, np.random.default_rng(777), {}
            )
            return self.status()

    def disable(self) -> OnlineStatus:
        with self._lock:
            self.enabled = False
            return self.status()

    def rebuild_shadow(self, num_bands: int) -> None:
        from ..schedulers.registry import create_scheduler

        self._shadow = create_scheduler(
            "priority", num_bands, np.random.default_rng(777), {}
        )

    def shadow_decide(self, context) -> int:
        if self._shadow is None or self._shadow.num_bands != context.num_bands:
            self.rebuild_shadow(context.num_bands)
        return int(self._shadow.decide(context).selected_band)

    def observe(self, time_slot: int, policy_reward: float, shadow_reward: float) -> str | None:
        if not self.enabled or self.guardrail is None:
            return None
        return self.guardrail.observe(time_slot, policy_reward, shadow_reward)

    def status(self) -> OnlineStatus:
        g = self.guardrail
        return OnlineStatus(
            enabled=self.enabled,
            active_scheduler=self.active_scheduler,
            shadow_scheduler="priority",
            policy_reward_ema=round(g.policy_ema, 4) if g else 0.0,
            shadow_reward_ema=round(g.shadow_ema, 4) if g else 0.0,
            margin=g.margin if g else 0.0,
            window=g.window if g else 0,
            breaches=g.breaches if g else 0,
            reverted=g.reverted if g else False,
            reverted_at_slot=g.reverted_at_slot if g else None,
            updates=g.updates if g else 0,
        )


_manager: OnlineManager | None = None


def get_online_manager() -> OnlineManager:
    global _manager
    if _manager is None:
        _manager = OnlineManager()
    return _manager


def _reset_for_tests() -> None:
    global _manager
    _manager = None
