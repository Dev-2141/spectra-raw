"""Emitter-track extraction (Extension Step 4).

Stitches per-band activity runs from the *observed* spectrum into persistent
tracks. Track ids are derived from the earliest run of a track, so re-running
extraction on more data keeps the same id even as the track hops in frequency.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .classify import classify_features
from .features import TrackFeatures, extract_features

_GAP_TOL = 14        # slots of silence before a run starts a new track
_BAND_TOL = 5        # band distance a run can be from a track's recent bands


@dataclass
class EmitterTrackObj:
    track_id: str
    first_seen: int
    last_seen: int
    bands: list[int]
    primary_band: int
    run_count: int
    active_slots: int
    threat: float
    is_synthetic_effect: bool
    features: TrackFeatures
    classification: dict
    library_matches: list[dict] = field(default_factory=list)

    def to_dict(self, current_t: int) -> dict:
        return {
            "track_id": self.track_id,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "age_slots": max(0, current_t - self.first_seen),
            "idle_slots": max(0, current_t - self.last_seen),
            "bands": self.bands,
            "primary_band": self.primary_band,
            "run_count": self.run_count,
            "active_slots": self.active_slots,
            "threat": round(self.threat, 3),
            "high_priority": self.threat >= 0.7,
            "is_synthetic_effect": self.is_synthetic_effect,
            "freq_behavior": self.features.hop_pattern,
            "spectral_shape": self.features.spectral_shape,
            "class": self.classification["class"],
            "class_confidence": self.classification["confidence"],
            "class_probabilities": self.classification["probabilities"],
            "modulation": self.classification["modulation"],
            "pri_estimate": self.features.pri_estimate,
            "pri_jitter": self.features.pri_jitter,
            "duty_cycle": self.features.duty_cycle,
            "snr_mean_db": self.features.snr_mean_db,
            "features": self.features.as_dict(),
            "library_matches": self.library_matches,
        }


def _flatten_runs(occ: np.ndarray, up_to_t: int) -> list[tuple[int, int, int]]:
    T = min(up_to_t + 1, occ.shape[0])
    out: list[tuple[int, int, int]] = []
    for b in range(occ.shape[1]):
        col = occ[:T, b].astype(bool)
        if not col.any():
            continue
        t = 0
        while t < T:
            if not col[t]:
                t += 1
                continue
            s = t
            while t < T and col[t]:
                t += 1
            out.append((s, t - 1, b))
    out.sort()
    return out


def extract_tracks(env, up_to_t: int, *, library_entries: list | None = None) -> list[EmitterTrackObj]:
    occ = getattr(env, "occupancy_observed", getattr(env, "occupancy"))
    snr = getattr(env, "snr_observed", getattr(env, "snr_db", None))
    synth = getattr(env, "is_synthetic_effect", None)
    threat_m = getattr(env, "threat", None)

    runs = _flatten_runs(occ, up_to_t)
    if not runs:
        return []

    # --- group runs into tracks ------------------------------------- #
    tracks: list[dict] = []  # {runs:[(s,e,b)], last_e:int, recent_bands:set}
    for s, e, b in runs:
        placed = False
        for tr in tracks:
            if s - tr["last_e"] <= _GAP_TOL and any(
                abs(b - rb) <= _BAND_TOL for rb in tr["recent_bands"]
            ):
                tr["runs"].append((s, e, b))
                tr["last_e"] = max(tr["last_e"], e)
                tr["recent_bands"] = set(list(tr["recent_bands"])[-5:] + [b])
                placed = True
                break
        if not placed:
            tracks.append({"runs": [(s, e, b)], "last_e": e, "recent_bands": {b}})

    out: list[EmitterTrackObj] = []
    for tr in tracks:
        tr_runs = sorted(tr["runs"])
        runs_by_band: dict[int, list[tuple[int, int]]] = {}
        for s, e, b in tr_runs:
            runs_by_band.setdefault(b, []).append((s, e))
        snr_by_band = (
            {b: float(snr[: up_to_t + 1, b].max()) for b in runs_by_band}
            if snr is not None
            else {}
        )
        feats = extract_features(runs_by_band, snr_by_band)

        band_list = sorted(runs_by_band)
        counts = {b: sum(e - s + 1 for s, e in v) for b, v in runs_by_band.items()}
        primary = max(counts, key=counts.get)
        first_seen = tr_runs[0][0]
        active = sum(e - s + 1 for s, e, _ in tr_runs)

        if threat_m is not None:
            th = float(
                max(
                    threat_m[s : e + 1, b].max() if e >= s else 0.0
                    for s, e, b in tr_runs
                )
            )
        else:
            th = 0.0
        is_synth = synth is not None and all(
            bool(synth[s : e + 1, b].all()) for s, e, b in tr_runs
        )

        matches: list[dict] = []
        if library_entries:
            from ..library.store import match_features

            matches = match_features(feats, library_entries)
            if th == 0.0 and matches:
                th = float(matches[0].get("threat", 0.0)) * float(matches[0]["score"])

        out.append(
            EmitterTrackObj(
                track_id=f"trk-{first_seen:05d}-{min(band_list):03d}",
                first_seen=first_seen,
                last_seen=tr["last_e"],
                bands=band_list,
                primary_band=int(primary),
                run_count=len(tr_runs),
                active_slots=active,
                threat=th,
                is_synthetic_effect=is_synth,
                features=feats,
                classification=classify_features(feats.vector()),
                library_matches=matches,
            )
        )

    out.sort(key=lambda o: (-o.threat, -o.last_seen))
    return out
