"""Report export helpers: CSV metrics table and a lightweight HTML summary."""

from __future__ import annotations

import csv
import io

from ..models.core import ComparisonReport

_CSV_COLUMNS = [
    "scheduler",
    "rank",
    "weighted_score",
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
]


def report_to_csv(report: ComparisonReport) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in report.metrics_table:
        writer.writerow(row)
    return buf.getvalue()


def report_to_html(report: ComparisonReport) -> str:
    head = (
        "<style>body{font-family:system-ui,sans-serif;background:#0a0e14;color:#c7d2e0;"
        "padding:24px}table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #1e2a3a;padding:6px 10px;text-align:right;font-size:13px}"
        "th{background:#111722;text-align:left}td:first-child,th:first-child{text-align:left}"
        ".win{color:#33d17a;font-weight:700}</style>"
    )
    rows = []
    for r in report.metrics_table:
        cls = ' class="win"' if r["scheduler"] == report.winner else ""
        rows.append(
            f"<tr{cls}><td>{r['scheduler']}</td><td>{r['rank']}</td>"
            f"<td>{r['weighted_score']}</td>"
            f"<td>{r['probability_of_detection']}</td>"
            f"<td>{r['false_alarm_rate']}</td>"
            f"<td>{r['interception_ratio']}</td>"
            f"<td>{r['average_intercept_delay']}</td>"
            f"<td>{r['average_reward']}</td>"
            f"<td>{r['high_priority_detection_rate']}</td>"
            f"<td>{r['missed_opportunity_count']}</td>"
            f"<td>{r['scan_coverage']}</td>"
            f"<td>{r['average_revisit_time']}</td>"
            f"<td>{r['correct_prediction_percentage']}</td></tr>"
        )
    ds = f" · replayed dataset {report.replayed_dataset}" if report.replayed_dataset else ""
    return (
        f"<!doctype html><meta charset='utf-8'><title>SPECTRA-SCAN comparison</title>{head}"
        f"<h2>SPECTRA-SCAN AI — strategy comparison</h2>"
        f"<p>seed {report.scenario_seed}{ds} · {report.number_of_bands} bands · "
        f"{report.steps} steps · winner <span class='win'>{report.winner}</span></p>"
        "<table><thead><tr>"
        "<th>scheduler</th><th>rank</th><th>score</th><th>P(det)</th><th>FAR</th>"
        "<th>intercept</th><th>delay</th><th>avg R</th><th>hi-pri</th><th>missed</th>"
        "<th>coverage</th><th>revisit</th><th>correct%</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )
