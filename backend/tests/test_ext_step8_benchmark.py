"""Extension Step 8: benchmark CI gate.

Fails if a headline metric drifts outside its frozen tolerance band, or if the
fixed-seed matrix stops being reproducible, or if the adaptive scheduler stops
beating the open-loop baseline on any preset.
"""

from __future__ import annotations

from scripts.benchmark import (
    BENCH_PRESETS,
    check_bands,
    run_benchmark,
)


def test_benchmark_matrix_is_deterministic():
    a = run_benchmark(seeds=[0, 101], steps=200)
    b = run_benchmark(seeds=[0, 101], steps=200)
    assert a["results"] == b["results"]
    assert a["headline"] == b["headline"]


def test_headline_metrics_stay_within_tolerance_bands():
    report = run_benchmark()
    violations = check_bands(report)
    assert violations == [], "; ".join(violations)


def test_priority_beats_round_robin_on_every_preset():
    report = run_benchmark()
    by_key = {
        (r["preset"], r["scheduler"]): r["metrics"]["average_reward"]["mean"]
        for r in report["results"]
    }
    for preset in BENCH_PRESETS:
        assert by_key[(preset, "priority")] > by_key[(preset, "round_robin")], preset
