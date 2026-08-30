"""Run-report rendering (JSON is returned as-is; CSV / HTML built here)."""

from __future__ import annotations

import csv
import io

_HTML_STYLE = (
    "<style>body{font-family:system-ui,sans-serif;background:#0a0e14;color:#c7d2e0;"
    "padding:24px;font-size:13px}h2{color:#33d17a}table{border-collapse:collapse;"
    "margin-top:12px}td,th{border:1px solid #1e2a3a;padding:5px 10px;text-align:left}"
    "th{background:#111722}code{color:#f0b429}</style>"
)


def _flatten(report: dict) -> list[tuple[str, str]]:
    m = report.get("metrics", {})
    env = report.get("environment_config", {})
    rcv = report.get("receiver_config", {})
    rows = [
        ("generated_at", report.get("generated_at", "")),
        ("scheduler", report.get("scheduler", "")),
        ("dataset_id", str(report.get("dataset_id"))),
        ("replay_mode", str(report.get("replay_mode"))),
        ("time_slot", str(report.get("time_slot"))),
        ("steps_run", str(report.get("steps_run"))),
        ("num_bands", str(env.get("num_bands"))),
        ("emitter_density", str(env.get("emitter_density"))),
        ("noise_floor_db", str(env.get("noise_floor_db"))),
        ("seed", str(env.get("seed"))),
        ("detection_threshold_db", str(rcv.get("detection_threshold_db"))),
        ("dwell_slots", str(rcv.get("dwell_slots"))),
        ("retune_delay_slots", str(rcv.get("retune_delay_slots"))),
    ]
    for k in (
        "probability_of_detection",
        "false_alarm_rate",
        "interception_ratio",
        "average_intercept_delay",
        "average_reward",
        "high_priority_detection_rate",
        "missed_opportunity_count",
        "scan_coverage",
        "average_revisit_time",
        "correct_prediction_percentage",
    ):
        rows.append((k, str(m.get(k))))
    return rows


def run_report_to_csv(report: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["key", "value"])
    w.writerows(_flatten(report))
    return buf.getvalue()


def run_report_to_html(report: dict) -> str:
    rows = "".join(
        f"<tr><td><code>{k}</code></td><td>{v}</td></tr>" for k, v in _flatten(report)
    )
    decisions = "".join(
        f"<tr><td>{d['time_slot']}</td><td>{d['selected_band']}</td>"
        f"<td>{d['outcome']}</td><td>{d['reward']}</td><td>{d['explanation']}</td></tr>"
        for d in report.get("recent_decisions", [])
    )
    return (
        f"<!doctype html><meta charset='utf-8'><title>SPECTRA-SCAN run report</title>"
        f"{_HTML_STYLE}<h2>SPECTRA-SCAN AI — run report</h2>"
        f"<p>{report.get('mode')}</p><table>{rows}</table>"
        f"<h3>Recent decisions</h3><table>"
        f"<tr><th>t</th><th>band</th><th>outcome</th><th>reward</th><th>explanation</th></tr>"
        f"{decisions}</table>"
    )
