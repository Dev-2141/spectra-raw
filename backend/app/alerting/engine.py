"""Alert rule evaluation and the acknowledged-alert store.

Evaluation is pull-based: the analysis snapshot (tracks + anomaly) is diffed
against what has already fired, so each rule raises at most one alert per
subject (track / band). Alerts have an open -> ack -> closed lifecycle.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

from ..models.core import Alert

_MAX_ALERTS = 500


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class AlertStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._alerts: list[Alert] = []
        self._fired: set[str] = set()          # dedup keys
        self._track_bands: dict[str, set[int]] = {}

    def reset(self) -> None:
        """New analysis context: clear rule dedup state, keep raised alerts.

        Track-derived alerts age out at the cap; externally raised alerts
        (e.g. the online guardrail) must survive a sim swap.
        """
        with self._lock:
            self._fired.clear()
            self._track_bands.clear()

    def clear_all(self) -> None:
        with self._lock:
            self._alerts.clear()
            self._fired.clear()
            self._track_bands.clear()

    def _add(self, rule_kind: str, severity: str, detail: str,
             track_id: str | None, band: int | None) -> Alert:
        alert = Alert(
            alert_id=f"alr_{uuid.uuid4().hex[:10]}", ts=_utc(), rule_kind=rule_kind,
            severity=severity, track_id=track_id, band=band, detail=detail, state="open",
        )
        self._alerts.append(alert)
        del self._alerts[:-_MAX_ALERTS]
        try:
            from ..stream.hub import get_stream_hub

            get_stream_hub().publish("alert", alert.model_dump())
        except Exception:  # pragma: no cover - streaming must never break alerting
            pass
        return alert

    def evaluate(self, tracks: list[dict], anomaly: dict, rules: list) -> list[Alert]:
        new: list[Alert] = []
        with self._lock:
            active = {r.kind: r for r in rules if r.enabled}

            for tr in tracks:
                tid = tr["track_id"]
                bands = set(tr.get("bands", []))
                prev_bands = self._track_bands.get(tid, set())

                if "new_emitter" in active:
                    key = f"new_emitter:{tid}"
                    if key not in self._fired:
                        self._fired.add(key)
                        new.append(self._add(
                            "new_emitter", active["new_emitter"].severity,
                            f"new track {tid} on band {tr['primary_band']} "
                            f"(class {tr['class']})", tid, tr["primary_band"]))

                if "priority_hit" in active and tr["threat"] >= active["priority_hit"].threshold:
                    key = f"priority_hit:{tid}"
                    if key not in self._fired:
                        self._fired.add(key)
                        new.append(self._add(
                            "priority_hit", active["priority_hit"].severity,
                            f"high-threat track {tid} (threat {tr['threat']:.2f})",
                            tid, tr["primary_band"]))

                if ("hop_detected" in active and prev_bands and bands - prev_bands):
                    key = f"hop_detected:{tid}:{min(bands)}:{max(bands)}"
                    if key not in self._fired:
                        self._fired.add(key)
                        new.append(self._add(
                            "hop_detected", active["hop_detected"].severity,
                            f"track {tid} moved to bands {sorted(bands - prev_bands)}",
                            tid, tr["primary_band"]))

                if "library_match" in active and tr.get("library_matches"):
                    top = tr["library_matches"][0]
                    if top["score"] >= active["library_match"].threshold:
                        key = f"library_match:{tid}:{top['entry_id']}"
                        if key not in self._fired:
                            self._fired.add(key)
                            new.append(self._add(
                                "library_match", active["library_match"].severity,
                                f"track {tid} matches {top['name']} "
                                f"(score {top['score']:.2f})", tid, tr["primary_band"]))

                self._track_bands[tid] = bands

            if "anomaly" in active and anomaly.get("ready"):
                for b in anomaly.get("anomalous_bands", []):
                    key = f"anomaly:{b}"
                    if key not in self._fired:
                        self._fired.add(key)
                        new.append(self._add(
                            "anomaly", active["anomaly"].severity,
                            f"spectrum anomaly on band {b}", None, int(b)))

        return new

    def raise_alert(
        self, rule_kind: str, severity: str, detail: str,
        track_id: str | None = None, band: int | None = None,
    ) -> Alert:
        with self._lock:
            return self._add(rule_kind, severity, detail, track_id, band)

    def list(self, state: str | None = None) -> list[Alert]:
        with self._lock:
            items = list(reversed(self._alerts))
        return [a for a in items if state is None or a.state == state]

    def unacked_count(self) -> int:
        with self._lock:
            return sum(1 for a in self._alerts if a.state == "open")

    def set_state(self, alert_id: str, state: str) -> Alert:
        with self._lock:
            for a in self._alerts:
                if a.alert_id == alert_id:
                    a.state = state
                    return a
        raise KeyError(alert_id)


_store: AlertStore | None = None


def get_alert_store() -> AlertStore:
    global _store
    if _store is None:
        _store = AlertStore()
    return _store


def evaluate_rules(tracks: list[dict], anomaly: dict, rules: list) -> list[Alert]:
    return get_alert_store().evaluate(tracks, anomaly, rules)


def _reset_for_tests() -> None:
    global _store
    _store = None
