"""Emitter-behaviour classifier (Extension Step 4).

A small scikit-learn RandomForest trained on synthetic feature vectors derived
from parametric emitters. It is trained on first use with a fixed seed and
cached in memory (and, best-effort, to a ``.joblib`` under ``analysis/models/``);
no binary needs to live in the repo. Always returns a probability vector and an
explicit ``unknown`` when the top probability is below threshold.

Modulation is *not* inferred from occupancy patterns — it is only known when a
library match supplies it, so it is reported as ``unknown`` here.
"""

from __future__ import annotations

import threading
from pathlib import Path

import numpy as np

from ..models.core import EmitterSpec, RFEnvironmentConfig
from .features import extract_features, runs_from_occupancy

BEHAVIOURS = ["constant", "burst", "periodic", "hopping", "low_duty", "priority"]
_UNKNOWN_THRESHOLD = 0.42
_MODEL_PATH = Path(__file__).parent / "models" / "emitter_clf.joblib"

_lock = threading.Lock()
_model = None


# --------------------------------------------------------------------------- #
# Synthetic training-set generation
# --------------------------------------------------------------------------- #
def _spec_for(behaviour: str, rng: np.random.Generator) -> EmitterSpec:
    home = int(rng.integers(4, 20))
    snr = float(rng.uniform(10, 22))
    if behaviour == "constant":
        return EmitterSpec(home_band=home, duty="blocks",
                           period_slots=int(rng.integers(30, 70)), snr_db=snr)
    if behaviour == "burst":
        return EmitterSpec(home_band=home, duty="bursts", snr_db=snr)
    if behaviour == "periodic":
        return EmitterSpec(home_band=home, duty="periodic",
                           period_slots=int(rng.integers(9, 34)),
                           pulse_slots=int(rng.integers(1, 4)),
                           pri_model=str(rng.choice(["fixed", "jitter"])),
                           pri_jitter_slots=int(rng.integers(1, 3)), snr_db=snr)
    if behaviour == "hopping":
        return EmitterSpec(home_band=home, agility="sweep",
                           hop_interval_slots=int(rng.integers(3, 10)),
                           sweep_span_bands=int(rng.integers(4, 10)),
                           duty="blocks", period_slots=int(rng.integers(6, 16)),
                           snr_db=snr)
    if behaviour == "low_duty":
        return EmitterSpec(home_band=home, duty="low_duty", snr_db=snr)
    return EmitterSpec(home_band=home, duty="low_duty", threat=0.85,
                       high_priority=True, period_slots=int(rng.integers(4, 12)),
                       snr_db=snr)


def _feature_row(spec: EmitterSpec, seed: int) -> list[float]:
    from ..simulation.environment import RFEnvironment

    cfg = RFEnvironmentConfig(num_bands=32, num_time_slots=360, seed=seed,
                              emitter_specs=[spec])
    env = RFEnvironment(cfg)
    runs = runs_from_occupancy(env.occupancy, env.num_time_slots - 1)
    snr = {b: float(env.snr_db[:, b].max()) for b in runs}
    return extract_features(runs, snr).vector()


def _build_dataset(n_per_class: int = 70):
    X: list[list[float]] = []
    y: list[str] = []
    for ci, beh in enumerate(BEHAVIOURS):
        for k in range(n_per_class):
            seed = 90_000 + ci * 1000 + k
            rng = np.random.default_rng(seed)
            row = _feature_row(_spec_for(beh, rng), seed)
            X.append(row)
            y.append(beh)
    return np.asarray(X, dtype=float), np.asarray(y)


def _train():
    from sklearn.ensemble import RandomForestClassifier

    X, y = _build_dataset()
    clf = RandomForestClassifier(
        n_estimators=60, max_depth=10, random_state=0, n_jobs=1
    )
    clf.fit(X, y)
    try:  # best-effort cache; not required
        import joblib

        _MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(clf, _MODEL_PATH)
    except Exception:
        pass
    return clf


def get_model():
    global _model
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        if _MODEL_PATH.is_file():
            try:
                import joblib

                _model = joblib.load(_MODEL_PATH)
                return _model
            except Exception:
                pass
        _model = _train()
        return _model


# --------------------------------------------------------------------------- #
def classify_features(feat_vector: list[float]) -> dict:
    """Return ``{class, confidence, probabilities, is_unknown, modulation}``."""
    clf = get_model()
    proba = clf.predict_proba([feat_vector])[0]
    classes = list(clf.classes_)
    probs = {c: round(float(p), 4) for c, p in zip(classes, proba)}
    top_i = int(np.argmax(proba))
    top_c = classes[top_i]
    top_p = float(proba[top_i])
    is_unknown = top_p < _UNKNOWN_THRESHOLD
    return {
        "class": "unknown" if is_unknown else top_c,
        "confidence": round(top_p, 4),
        "probabilities": probs,
        "is_unknown": is_unknown,
        "modulation": "unknown",
    }
