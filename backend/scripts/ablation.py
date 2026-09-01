"""Ablation runner — every scheduler vs the two baselines, every preset.

For each (preset, scheduler) cell it runs N seeds and reports mean +/- 95% CI
for the mission-relevant metrics, plus the delta of each adaptive scheduler
against the ``round_robin`` and ``random`` baselines. Feeds the ablation table
in the mission report and ``docs/VALIDATION.md``.

Run:  python -m scripts.ablation           (writes backend/data/ablation/latest.json)
      python -m scripts.ablation --quick
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings
from app.schedulers.registry import available_schedulers
from app.simulation.engine import Simulation
from app.simulation.presets import preset_names

BASELINES = ("round_robin", "random")
ABLATION_METRICS = [
    "average_reward",
    "interception_ratio",
    "high_priority_detection_rate",
    "probability_of_detection",
    "false_alarm_rate",
    "missed_opportunity_count",
]
DEFAULT_SEEDS = [0, 101, 202, 303, 404]
DEFAULT_STEPS = 400


def _ci95(vals: list[float]) -> float:
    n = len(vals)
    if n < 2:
        return 0.0
    return round(1.96 * statistics.stdev(vals) / (n**0.5), 4)


def _cell(preset: str, scheduler: str, seeds: list[int], steps: int) -> dict:
    from app.simulation.presets import get_preset

    env_base, rcv = get_preset(preset)
    acc: dict[str, list[float]] = {m: [] for m in ABLATION_METRICS}
    for s in seeds:
        env = env_base.model_copy(update={"seed": env_base.seed + s})
        sim = Simulation(env_config=env, receiver_config=rcv, scheduler_name=scheduler)
        sim.run(steps)
        m = sim.metrics_snapshot().model_dump()
        for name in ABLATION_METRICS:
            acc[name].append(float(m[name]))
    return {
        name: {
            "mean": round(statistics.fmean(v), 4),
            "ci95": _ci95(v),
        }
        for name, v in acc.items()
    }


def run_ablation(
    *,
    presets: list[str] | None = None,
    schedulers: list[str] | None = None,
    seeds: list[int] | None = None,
    steps: int = DEFAULT_STEPS,
) -> dict:
    presets = presets or preset_names()
    avail = set(available_schedulers())
    schedulers = schedulers or [s for s in available_schedulers()]
    schedulers = [s for s in schedulers if s in avail]
    seeds = seeds if seeds is not None else DEFAULT_SEEDS

    rows: list[dict] = []
    for preset in presets:
        base_cells = {b: _cell(preset, b, seeds, steps) for b in BASELINES if b in avail}
        for sch in schedulers:
            cell = base_cells[sch] if sch in base_cells else _cell(preset, sch, seeds, steps)
            deltas = {
                b: round(
                    cell["average_reward"]["mean"]
                    - base_cells[b]["average_reward"]["mean"],
                    4,
                )
                for b in base_cells
            }
            rows.append(
                {
                    "preset": preset,
                    "scheduler": sch,
                    "is_baseline": sch in BASELINES,
                    "n_seeds": len(seeds),
                    "metrics": cell,
                    "avg_reward_delta_vs": deltas,
                }
            )

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config": {
            "presets": presets,
            "schedulers": schedulers,
            "seeds": seeds,
            "steps": steps,
        },
        "baselines": list(BASELINES),
        "rows": rows,
    }


def _out_path() -> Path:
    d = get_settings().data_dir / "ablation"
    d.mkdir(parents=True, exist_ok=True)
    return d / "latest.json"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SPECTRA-SCAN ablation runner")
    ap.add_argument("--quick", action="store_true", help="3 seeds, 250 steps, 2 presets")
    args = ap.parse_args(argv)

    if args.quick:
        report = run_ablation(
            presets=preset_names()[:2], seeds=DEFAULT_SEEDS[:3], steps=250
        )
    else:
        report = run_ablation()

    path = _out_path()
    path.write_text(json.dumps(report, indent=2), "utf-8")
    print(f"ablation written -> {path}  ({len(report['rows'])} cells)")
    for r in report["rows"]:
        d = r["metrics"]["average_reward"]
        vs = " ".join(f"{k}:{v:+.2f}" for k, v in r["avg_reward_delta_vs"].items())
        print(
            f"  {r['preset'][:28]:28} {r['scheduler']:16} "
            f"avgR={d['mean']:9.3f} +/-{d['ci95']:.2f}   {vs}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
