"""Next-activation forecast for periodic tracks (Extension Step 4).

For any track that looks periodic (low PRI jitter, a usable PRI estimate),
project the next few activation slots. The result is exposed on ``/api/forecast``
and can be fed to the priority scheduler as a per-band pre-position bonus.
"""

from __future__ import annotations

import numpy as np

_MAX_JITTER = 0.35
_HORIZON = 4


def forecast_tracks(tracks: list, current_t: int) -> list[dict]:
    out: list[dict] = []
    for tr in tracks:
        f = tr.features
        pri = float(f.pri_estimate)
        if pri < 2.0 or f.pri_jitter > _MAX_JITTER or f.run_count < 3:
            continue
        # phase-align to the most recent activation
        k = int(np.ceil((current_t - tr.last_seen) / pri))
        next_slots = [int(round(tr.last_seen + (k + i) * pri)) for i in range(_HORIZON)]
        next_slots = [s for s in next_slots if s >= current_t]
        if not next_slots:
            continue
        confidence = round(float(max(0.0, 1.0 - f.pri_jitter / _MAX_JITTER)), 3)
        out.append(
            {
                "track_id": tr.track_id,
                "band": tr.primary_band,
                "pri_slots": round(pri, 2),
                "pri_jitter": f.pri_jitter,
                "next_slots": next_slots,
                "slots_until_next": next_slots[0] - current_t,
                "confidence": confidence,
            }
        )
    out.sort(key=lambda d: d["slots_until_next"])
    return out


def preposition_bonus(forecasts: list[dict], num_bands: int, current_t: int) -> np.ndarray:
    """Per-band bonus in [0, 1] — highest when a periodic emission is imminent."""
    bonus = np.zeros(num_bands, dtype=np.float64)
    for fc in forecasts:
        b = int(fc["band"])
        if 0 <= b < num_bands:
            dt = max(0, fc["slots_until_next"])
            bonus[b] = max(bonus[b], fc["confidence"] * float(np.exp(-dt / 3.0)))
    return bonus
