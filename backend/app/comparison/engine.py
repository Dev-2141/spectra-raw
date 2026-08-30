"""Strategy comparison engine.

Runs several schedulers against the *same* scenario (identical environment seed
or the same replayed dataset) and produces a comparable metrics table, time
series, and a weighted-score winner. No metric here is hardcoded per strategy.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from ..models.core import (
    ComparisonEntry,
    ComparisonReport,
    ComparisonSeries,
    RFEnvironmentConfig,
    ReceiverConfig,
    SchedulerMetrics,
)
from ..simulation.engine import Simulation
from ..simulation.environment import RFEnvironment

# Higher is better for all; "missed" and "delay" are inverted before weighting.
SCORE_WEIGHTS: dict[str, float] = {
    "interception_ratio": 0.35,
    "high_priority_detection_rate": 0.25,
    "average_reward": 0.20,
    "missed_opportunity_count": 0.10,   # inverted
    "average_intercept_delay": 0.10,    # inverted
}


def _minmax(values: list[float]) -> list[float]:
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [0.5 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def _sample_series(history, n_points: int) -> ComparisonSeries:
    if not history:
        return ComparisonSeries(
            time_slot=[], average_reward=[], detection_rate=[],
            interception_ratio=[], scan_coverage=[],
        )
    idx = np.unique(
        np.linspace(0, len(history) - 1, min(n_points, len(history))).astype(int)
    )
    ts, ar, dr, ir, cov = [], [], [], [], []
    for i in idx:
        m = history[i].metrics
        ts.append(int(history[i].time_slot))
        ar.append(round(m.average_reward, 4))
        dr.append(round(m.probability_of_detection, 4))
        ir.append(round(m.interception_ratio, 4))
        cov.append(round(m.scan_coverage, 4))
    return ComparisonSeries(
        time_slot=ts, average_reward=ar, detection_rate=dr,
        interception_ratio=ir, scan_coverage=cov,
    )


def compare_strategies(
    env_config: RFEnvironmentConfig,
    receiver_config: ReceiverConfig,
    schedulers: list[str],
    steps: int,
    *,
    series_points: int = 60,
    scheduler_params: dict[str, dict] | None = None,
    env_factory: Callable[[], RFEnvironment] | None = None,
    replayed_dataset: str | None = None,
) -> ComparisonReport:
    scheduler_params = scheduler_params or {}
    raw: list[tuple[str, SchedulerMetrics, ComparisonSeries]] = []

    n_bands = env_config.num_bands
    n_slots = env_config.num_time_slots

    for name in schedulers:
        env = env_factory() if env_factory is not None else None
        sim = Simulation(
            env_config=env_config,
            receiver_config=receiver_config,
            scheduler_name=name,
            scheduler_params=scheduler_params.get(name, {}),
            env_instance=env,
        )
        if env is not None:
            n_bands = env.num_bands
            n_slots = env.num_time_slots
        sim.run(steps)
        metrics = sim.metrics_snapshot()
        series = _sample_series(sim.history, series_points)
        raw.append((name, metrics, series))

    # --- weighted score (min-max normalised across the compared set) ---- #
    def col(attr: str) -> list[float]:
        return [float(getattr(m, attr)) for _, m, _ in raw]

    norm = {
        "interception_ratio": _minmax(col("interception_ratio")),
        "high_priority_detection_rate": _minmax(col("high_priority_detection_rate")),
        "average_reward": _minmax(col("average_reward")),
        "missed_opportunity_count": [
            1.0 - v for v in _minmax(col("missed_opportunity_count"))
        ],
        "average_intercept_delay": [
            1.0 - v for v in _minmax(col("average_intercept_delay"))
        ],
    }
    scores = [
        sum(SCORE_WEIGHTS[k] * norm[k][i] for k in SCORE_WEIGHTS)
        for i in range(len(raw))
    ]

    order = sorted(range(len(raw)), key=lambda i: scores[i], reverse=True)
    rank_of = {i: pos + 1 for pos, i in enumerate(order)}

    entries: list[ComparisonEntry] = []
    table: list[dict] = []
    for i, (name, m, series) in enumerate(raw):
        entries.append(
            ComparisonEntry(
                scheduler=name,
                metrics=m,
                series=series,
                weighted_score=round(scores[i], 4),
                rank=rank_of[i],
            )
        )
        table.append(
            {
                "scheduler": name,
                "rank": rank_of[i],
                "weighted_score": round(scores[i], 4),
                "probability_of_detection": m.probability_of_detection,
                "false_alarm_rate": m.false_alarm_rate,
                "interception_ratio": m.interception_ratio,
                "average_intercept_delay": m.average_intercept_delay,
                "average_reward": m.average_reward,
                "high_priority_detection_rate": m.high_priority_detection_rate,
                "missed_opportunity_count": m.missed_opportunity_count,
                "scan_coverage": m.scan_coverage,
                "average_revisit_time": m.average_revisit_time,
                "correct_prediction_percentage": m.correct_prediction_percentage,
            }
        )

    entries.sort(key=lambda e: e.rank)
    table.sort(key=lambda r: r["rank"])
    ranking = [raw[i][0] for i in order]

    return ComparisonReport(
        scenario_seed=env_config.seed,
        replayed_dataset=replayed_dataset,
        number_of_bands=n_bands,
        number_of_time_slots=n_slots,
        steps=steps,
        schedulers=schedulers,
        entries=entries,
        metrics_table=table,
        winner=ranking[0] if ranking else "",
        ranking=ranking,
        score_weights=SCORE_WEIGHTS,
    )
