"""Monte-Carlo evaluation (Extension Step 3).

Runs a scenario across N seeds x the scheduler set and reports, per scheduler,
the mean / std / 95% CI of every headline metric plus a win-rate (fraction of
seeds where that scheduler had the best average reward). Deterministic for a
given seed set; results are cached in-process by (scenario, seeds, schedulers).
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone

import numpy as np

from ..models.core import (
    EWEffectSpec,
    MetricAggregate,
    MonteCarloEntry,
    MonteCarloReport,
    RFEnvironmentConfig,
    ReceiverConfig,
)
from ..simulation.engine import Simulation

_METRICS = (
    "average_reward",
    "probability_of_detection",
    "false_alarm_rate",
    "interception_ratio",
    "average_intercept_delay",
    "high_priority_detection_rate",
    "missed_opportunity_count",
    "scan_coverage",
)

_CACHE: dict[tuple, MonteCarloReport] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _agg(name: str, values: list[float]) -> MetricAggregate:
    arr = np.asarray(values, dtype=float)
    n = int(arr.size)
    mean = float(arr.mean()) if n else 0.0
    std = float(arr.std(ddof=1)) if n > 1 else 0.0
    half = 1.96 * std / math.sqrt(n) if n > 1 else 0.0
    return MetricAggregate(
        metric=name,
        mean=round(mean, 4),
        std=round(std, 4),
        ci95_low=round(mean - half, 4),
        ci95_high=round(mean + half, 4),
        n=n,
    )


def run_montecarlo(
    *,
    environment: RFEnvironmentConfig,
    receiver: ReceiverConfig,
    effects: list[EWEffectSpec],
    schedulers: list[str],
    seeds: list[int],
    steps: int,
    scenario_id: str | None = None,
    scenario_name: str = "",
) -> MonteCarloReport:
    key = (
        scenario_id,
        environment.model_dump_json(),
        receiver.model_dump_json(),
        tuple(e.model_dump_json() for e in effects),
        tuple(schedulers),
        tuple(seeds),
        steps,
    )
    if key in _CACHE:
        return _CACHE[key]

    per_metric: dict[str, dict[str, list[float]]] = {
        s: {m: [] for m in _METRICS} for s in schedulers
    }
    wins = {s: 0 for s in schedulers}

    for seed in seeds:
        seed_rewards: dict[str, float] = {}
        for name in schedulers:
            env_cfg = environment.model_copy(update={"seed": int(seed)})
            sim = Simulation(
                env_config=env_cfg,
                receiver_config=receiver,
                scheduler_name=name,
                ew_effects=[e for e in effects] or None,
            )
            sim.run(steps)
            m = sim.metrics_snapshot()
            for metric in _METRICS:
                per_metric[name][metric].append(float(getattr(m, metric)))
            seed_rewards[name] = m.average_reward
        best = max(seed_rewards, key=seed_rewards.get)
        wins[best] += 1

    entries: list[MonteCarloEntry] = []
    for name in schedulers:
        entries.append(
            MonteCarloEntry(
                scheduler=name,
                aggregates=[_agg(m, per_metric[name][m]) for m in _METRICS],
                win_rate=round(wins[name] / len(seeds), 4) if seeds else 0.0,
            )
        )

    def _mean_reward(entry: MonteCarloEntry) -> float:
        for a in entry.aggregates:
            if a.metric == "average_reward":
                return a.mean
        return 0.0

    ranking = [e.scheduler for e in sorted(entries, key=_mean_reward, reverse=True)]
    report = MonteCarloReport(
        montecarlo_id=f"mc_{uuid.uuid4().hex[:10]}",
        created_at=_utc_now(),
        scenario_id=scenario_id,
        scenario_name=scenario_name,
        schedulers=schedulers,
        seeds=seeds,
        steps=steps,
        number_of_bands=environment.num_bands,
        entries=entries,
        ranking=ranking,
        winner=ranking[0] if ranking else "",
    )
    _CACHE[key] = report
    return report


def get_cached(montecarlo_id: str) -> MonteCarloReport | None:
    for rep in _CACHE.values():
        if rep.montecarlo_id == montecarlo_id:
            return rep
    return None


def montecarlo_to_csv(rep: MonteCarloReport) -> str:
    rows = ["scheduler,metric,mean,std,ci95_low,ci95_high,n,win_rate"]
    for e in rep.entries:
        for a in e.aggregates:
            rows.append(
                f"{e.scheduler},{a.metric},{a.mean},{a.std},{a.ci95_low},"
                f"{a.ci95_high},{a.n},{e.win_rate}"
            )
    return "\n".join(rows) + "\n"


def montecarlo_to_html(rep: MonteCarloReport) -> str:
    head = (
        "<html><head><meta charset='utf-8'><title>Monte Carlo — "
        f"{rep.scenario_name or rep.scenario_id or 'scenario'}</title>"
        "<style>body{font:13px system-ui;margin:2rem;background:#0a0e14;color:#c7d2e0}"
        "table{border-collapse:collapse}td,th{border:1px solid #1e2a3a;padding:4px 8px}"
        "th{color:#6b7a8f;font-weight:400}caption{margin-bottom:.5rem;color:#33d17a}"
        "</style></head><body>"
    )
    body = [
        head,
        f"<h2>Monte Carlo — {rep.scenario_name or rep.scenario_id or ''}</h2>",
        f"<p>{len(rep.seeds)} seeds × {len(rep.schedulers)} schedulers · "
        f"{rep.steps} steps · winner <b>{rep.winner}</b></p>",
    ]
    for e in rep.entries:
        body.append(f"<table><caption>{e.scheduler} — win rate {e.win_rate}</caption>")
        body.append("<tr><th>metric</th><th>mean</th><th>95% CI</th><th>std</th></tr>")
        for a in e.aggregates:
            body.append(
                f"<tr><td>{a.metric}</td><td>{a.mean}</td>"
                f"<td>[{a.ci95_low}, {a.ci95_high}]</td><td>{a.std}</td></tr>"
            )
        body.append("</table><br>")
    body.append("</body></html>")
    return "".join(body)
