"""Benchmark suite — fixed scenarios x fixed seeds x schedulers.

Produces a JSON report of per-metric mean / std / 95% CI for a small, frozen
matrix. ``test_ext_step8_benchmark.py`` gates CI against the tolerance bands in
:data:`HEADLINE_BANDS`: if a headline number drifts outside its band the build
fails, protecting the paper's claims from silent regression.

Run:  python -m scripts.benchmark            (writes backend/data/benchmark/latest.json)
      python -m scripts.benchmark --quick    (2 seeds, shorter — for a fast check)
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings
from app.simulation.engine import Simulation
from app.simulation.presets import get_preset

# --- frozen matrix --------------------------------------------------------- #
BENCH_PRESETS = [
    "Periodic Radar-Like Challenge",
    "Frequency Hopping Challenge",
    "Dense Emitter Environment",
]
BENCH_SCHEDULERS = ["round_robin", "priority", "ucb_bandit"]
BENCH_SEEDS = [0, 101, 202]        # added to each preset's own seed
BENCH_STEPS = 400
BENCH_METRICS = [
    "average_reward",
    "interception_ratio",
    "high_priority_detection_rate",
    "probability_of_detection",
    "missed_opportunity_count",
]

# Headline tolerance bands: (metric, scheduler) -> (lo, hi) on the cross-preset
# mean. Bands are wide enough for RNG jitter, tight enough to catch a real
# regression. Regenerate with --emit-bands after an intentional change.
HEADLINE_BANDS: dict[tuple[str, str], tuple[float, float]] = {
    ("average_reward", "priority"): (-55.0, -31.0),
    ("average_reward", "round_robin"): (-66.0, -40.0),
    ("interception_ratio", "priority"): (0.0, 0.15),
    ("probability_of_detection", "priority"): (0.78, 1.0),
}


def _ci95(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    return round(1.96 * statistics.stdev(values) / (n**0.5), 4)


def _run_cell(preset: str, scheduler: str, seeds: list[int], steps: int) -> dict:
    env_base, rcv = get_preset(preset)
    per_metric: dict[str, list[float]] = {m: [] for m in BENCH_METRICS}
    for s in seeds:
        env = env_base.model_copy(update={"seed": env_base.seed + s})
        sim = Simulation(
            env_config=env, receiver_config=rcv, scheduler_name=scheduler
        )
        sim.run(steps)
        m = sim.metrics_snapshot().model_dump()
        for name in BENCH_METRICS:
            per_metric[name].append(float(m[name]))
    return {
        "preset": preset,
        "scheduler": scheduler,
        "n": len(seeds),
        "metrics": {
            name: {
                "mean": round(statistics.fmean(vals), 4),
                "std": round(statistics.pstdev(vals), 4),
                "ci95": _ci95(vals),
                "values": [round(v, 4) for v in vals],
            }
            for name, vals in per_metric.items()
        },
    }


def run_benchmark(
    *,
    presets: list[str] | None = None,
    schedulers: list[str] | None = None,
    seeds: list[int] | None = None,
    steps: int = BENCH_STEPS,
) -> dict:
    """Run the matrix and return the report dict (no file written)."""
    presets = presets or BENCH_PRESETS
    schedulers = schedulers or BENCH_SCHEDULERS
    seeds = seeds if seeds is not None else BENCH_SEEDS

    results = [
        _run_cell(p, sch, seeds, steps) for p in presets for sch in schedulers
    ]

    # cross-preset headline means per scheduler
    headline: dict[str, dict[str, float]] = {}
    for sch in schedulers:
        cells = [r for r in results if r["scheduler"] == sch]
        headline[sch] = {
            name: round(
                statistics.fmean(c["metrics"][name]["mean"] for c in cells), 4
            )
            for name in BENCH_METRICS
        }

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config": {
            "presets": presets,
            "schedulers": schedulers,
            "seeds": seeds,
            "steps": steps,
        },
        "results": results,
        "headline": headline,
        "bands": {f"{m}|{s}": list(b) for (m, s), b in HEADLINE_BANDS.items()},
    }


def check_bands(report: dict) -> list[str]:
    """Return a list of human-readable band violations (empty == pass)."""
    violations: list[str] = []
    for (metric, sch), (lo, hi) in HEADLINE_BANDS.items():
        val = report["headline"].get(sch, {}).get(metric)
        if val is None:
            violations.append(f"{metric}/{sch}: missing from report")
        elif not (lo <= val <= hi):
            violations.append(f"{metric}/{sch}: {val} outside [{lo}, {hi}]")
    return violations


def _out_path() -> Path:
    d = get_settings().data_dir / "benchmark"
    d.mkdir(parents=True, exist_ok=True)
    return d / "latest.json"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SPECTRA-SCAN benchmark suite")
    ap.add_argument("--quick", action="store_true", help="2 seeds, 250 steps")
    ap.add_argument("--emit-bands", action="store_true", help="print fresh HEADLINE_BANDS")
    args = ap.parse_args(argv)

    if args.quick:
        report = run_benchmark(seeds=BENCH_SEEDS[:2], steps=250)
    else:
        report = run_benchmark()

    path = _out_path()
    path.write_text(json.dumps(report, indent=2), "utf-8")

    print(f"benchmark written -> {path}")
    for sch, h in report["headline"].items():
        print(
            f"  {sch:16} avgR={h['average_reward']:8.3f}  "
            f"intercept={h['interception_ratio']:.3f}  "
            f"P(det)={h['probability_of_detection']:.3f}  "
            f"missed={h['missed_opportunity_count']:.0f}"
        )

    if args.emit_bands:
        print("\nHEADLINE_BANDS = {")
        for (m, s) in HEADLINE_BANDS:
            v = report["headline"][s][m]
            pad = max(0.15 * abs(v), 0.05)
            print(f'    ("{m}", "{s}"): ({round(v - pad, 3)}, {round(v + pad, 3)}),')
        print("}")

    violations = check_bands(report)
    if violations:
        print("\nBAND VIOLATIONS:")
        for v in violations:
            print(f"  - {v}")
        return 1
    print("\nall headline bands OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
