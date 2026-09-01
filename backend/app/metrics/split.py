"""Metric split — simulation (ground-truth) vs live (proxy) — and recomputation.

Step 8 finalises which metrics are only meaningful when synthetic ground truth
exists (``simulation`` mode) and which survive with a receive-only SDR feed and
no ground truth (``live_es`` mode).

Every metric here has:

* a one-line **definition** (also mirrored in ``docs/REFERENCE.md`` §I.9a), and
* an **independent reimplementation** that recomputes it from the raw
  per-step history so a test can assert equality with the live snapshot
  (cross-cutting requirement #4).

Nothing in this module touches hardware or the network.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..simulation.reward import HIGH_PRIORITY_THREAT, compute_proxy_reward

# --------------------------------------------------------------------------- #
# Canonical definitions
# --------------------------------------------------------------------------- #
SIM_METRICS: dict[str, str] = {
    "probability_of_detection": (
        "hits / scans that landed on a truly active band"
    ),
    "false_alarm_rate": (
        "false alarms / scans that landed on an inactive band"
    ),
    "interception_ratio": (
        "distinct emitter events detected at least once / emitter events begun so far"
    ),
    "average_intercept_delay": (
        "mean (first_detection_slot - event.start) over detected events, in slots"
    ),
    "high_priority_detection_rate": (
        "high-priority events detected / high-priority events begun so far "
        f"(high priority = flag set or threat >= {HIGH_PRIORITY_THREAT})"
    ),
    "missed_opportunity_count": (
        "sum over steps of (active bands this slot that were not the scanned band)"
    ),
    "correct_prediction_percentage": (
        "100 * correct predicted_active flags / steps that carried a prediction"
    ),
    "scan_coverage": "distinct bands scanned / total bands (shared with live)",
    "average_revisit_time": (
        "mean gap (slots) between consecutive visits to the same band "
        "(shared with live)"
    ),
    "detection_under_effect_rate": (
        "real signals detected while a simulated EW effect covered the band / "
        "such (truth-active, effect-covered) scans"
    ),
    "spoof_deception_rate": (
        "scans that 'detected' energy on a truth-inactive, effect-covered band / "
        "synthetic-effect scans (share of scans the spoof/jam fooled)"
    ),
    "df_cep_km": "median geolocation error vs truth position (circular error probable)",
    "df_rmse_km": "root-mean-square geolocation error vs truth position",
}

LIVE_METRICS: dict[str, str] = {
    "occupancy_estimate": (
        "fraction of (scan) observations flagged above threshold — no truth claim"
    ),
    "scan_coverage": "distinct bands scanned / total bands",
    "average_observed_snr_db": "mean measured SNR over scans that cleared threshold",
    "average_revisit_time": "mean gap (slots) between consecutive visits to the same band",
    "above_threshold_detections": "count of scans the receiver flagged (detection or false alarm)",
    "average_proxy_reward": (
        "mean of compute_proxy_reward() per step — rewards stable above-threshold "
        "detections, penalises empty scans / excess retuning; NO ground truth"
    ),
    "recording_duration_s": "wall-clock span of the ingested recording (n/a in pure sim)",
    "frame_rate_hz": "mean sweep-frame rate from the SDR source (n/a in pure sim)",
    "alerts_open": "current count of un-acknowledged alerts",
    "alerts_total": "alerts raised over the session",
    "policy_vs_shadow_margin": (
        "online policy proxy-reward EMA minus the priority shadow-baseline EMA"
    ),
}


def metric_split() -> dict[str, Any]:
    """Serialisable split for ``GET /api/report/metrics/split``."""
    return {
        "simulation": [{"name": k, "definition": v} for k, v in SIM_METRICS.items()],
        "live": [{"name": k, "definition": v} for k, v in LIVE_METRICS.items()],
        "note": (
            "Simulation metrics need synthetic ground truth and read 'n/a' with a "
            "receive-only SDR feed. Live metrics are computable from observations "
            "alone. Overlapping names (scan_coverage, average_revisit_time) share a "
            "definition across both modes."
        ),
    }


# --------------------------------------------------------------------------- #
# Independent recomputation from raw history
# --------------------------------------------------------------------------- #
def _iter_steps(history: list) -> list[dict]:
    """Normalise ``Simulation.history`` entries to plain dicts."""
    rows: list[dict] = []
    for r in history:
        d, det = r.decision, r.detection
        rows.append(
            {
                "t": int(r.time_slot),
                "scanned_band": int(det.band),
                "true_active": bool(det.true_active),
                "detected": bool(det.detected),
                "false_alarm": bool(det.false_alarm),
                "predicted_active": d.predicted_active,
                "measured_snr_db": float(det.measured_snr_db),
                "reward": float(r.reward),
                "retuned": bool(r.retuned),
            }
        )
    return rows


def recompute_sim_metrics(history: list, env) -> dict[str, float]:
    """Reimplement the ground-truth metric block from ``history`` + ``env``.

    Mirrors :meth:`app.metrics.tracker.MetricsTracker.snapshot` without reusing
    any of its state.
    """
    rows = _iter_steps(history)
    up_to_t = rows[-1]["t"] if rows else 0

    active_scans = sum(1 for s in rows if s["true_active"])
    inactive_scans = len(rows) - active_scans
    hits = sum(1 for s in rows if s["true_active"] and s["detected"])
    false_alarms = sum(1 for s in rows if (not s["true_active"]) and s["false_alarm"])

    predictions = [s for s in rows if s["predicted_active"] is not None]
    correct = sum(
        1 for s in predictions if bool(s["predicted_active"]) == s["true_active"]
    )

    # --- emitter-event interception (independent bookkeeping) ------------- #
    events = [e for e in env.events if e.start <= up_to_t]
    first_det: dict[int, int] = {}
    for s in rows:
        if not (s["true_active"] and s["detected"]):
            continue
        for i, e in enumerate(events):
            if e.band == s["scanned_band"] and e.start <= s["t"] <= e.end and i not in first_det:
                first_det[i] = s["t"]
                break
    detected_events = len(first_det)
    delays = [first_det[i] - events[i].start for i in first_det]

    hp_idx = [
        i
        for i, e in enumerate(events)
        if e.high_priority or e.threat >= HIGH_PRIORITY_THREAT
    ]
    hp_detected = sum(1 for i in hp_idx if i in first_det)

    # --- missed opportunities ------------------------------------------- #
    missed = 0
    for s in rows:
        for b in env.active_bands(s["t"]):
            if b != s["scanned_band"]:
                missed += 1

    # --- coverage / revisit ------------------------------------------- #
    visited = {s["scanned_band"] for s in rows}
    visit_slots: dict[int, list[int]] = defaultdict(list)
    for s in rows:
        visit_slots[s["scanned_band"]].append(s["t"])
    gaps = [
        b - a
        for slots in visit_slots.values()
        if len(slots) >= 2
        for a, b in zip(slots, slots[1:])
    ]

    n_bands = env.num_bands
    return {
        "probability_of_detection": round(hits / active_scans, 4) if active_scans else 0.0,
        "false_alarm_rate": round(false_alarms / inactive_scans, 4) if inactive_scans else 0.0,
        "interception_ratio": round(detected_events / len(events), 4) if events else 0.0,
        "average_intercept_delay": round(sum(delays) / len(delays), 3) if delays else 0.0,
        "high_priority_detection_rate": round(hp_detected / len(hp_idx), 4) if hp_idx else 0.0,
        "missed_opportunity_count": missed,
        "scan_coverage": round(len(visited) / n_bands, 4) if n_bands else 0.0,
        "average_revisit_time": round(sum(gaps) / len(gaps), 3) if gaps else 0.0,
        "correct_prediction_percentage": round(100.0 * correct / len(predictions), 2)
        if predictions
        else 0.0,
    }


def recompute_live_metrics(history: list) -> dict[str, float]:
    """Reimplement the proxy metric block computable without ground truth.

    Only the history-derivable subset of :data:`LIVE_METRICS` is returned;
    frame-rate / recording-duration / alert counts come from other subsystems.
    """
    rows = _iter_steps(history)
    if not rows:
        return {
            "occupancy_estimate": 0.0,
            "scan_coverage": 0.0,
            "average_observed_snr_db": 0.0,
            "above_threshold_detections": 0,
            "average_proxy_reward": 0.0,
        }

    flagged = [s for s in rows if s["detected"] or s["false_alarm"]]
    snr_vals = [s["measured_snr_db"] for s in flagged]

    proxy = 0.0
    for s in rows:
        obs_active = s["detected"]  # no truth — "observed active" == receiver flagged it
        r, _ = compute_proxy_reward(
            detected=s["detected"], observed_active=obs_active, retuned=s["retuned"]
        )
        proxy += r

    visited = {s["scanned_band"] for s in rows}
    n_bands = max(s["scanned_band"] for s in rows) + 1
    visit_slots: dict[int, list[int]] = defaultdict(list)
    for s in rows:
        visit_slots[s["scanned_band"]].append(s["t"])
    gaps = [
        b - a
        for slots in visit_slots.values()
        if len(slots) >= 2
        for a, b in zip(slots, slots[1:])
    ]

    return {
        "occupancy_estimate": round(len(flagged) / len(rows), 4),
        "scan_coverage": round(len(visited) / n_bands, 4),
        "average_observed_snr_db": round(sum(snr_vals) / len(snr_vals), 3) if snr_vals else 0.0,
        "average_revisit_time": round(sum(gaps) / len(gaps), 3) if gaps else 0.0,
        "above_threshold_detections": len(flagged),
        "average_proxy_reward": round(proxy / len(rows), 4),
    }
