"""Report rendering.

Two products:

* the lightweight **run report** (a snapshot of the live simulation) — CSV / HTML
  helpers unchanged from Step 5; and
* the Step 8 **mission report** — a self-contained HTML (print-to-PDF ready, zero
  external assets) built from a persisted :class:`~app.store.sessions.Session`:
  summary, timeline, the sim/live metric split, a scheduler-vs-baseline table
  with mean +/- CI, tracks, DF fixes, alerts, server-rendered SVG charts,
  assumptions and limitations.
"""

from __future__ import annotations

import csv
import html
import io
import statistics
from datetime import datetime, timezone

from .metrics.split import LIVE_METRICS, SIM_METRICS

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


# ========================================================================= #
# Step 8 — mission report
# ========================================================================= #
_DASH = "—"

_MISSION_STYLE = (
    "<style>"
    "*{box-sizing:border-box}"
    "body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#0a0e14;"
    "color:#c7d2e0;margin:0;padding:32px;font-size:13px;line-height:1.5}"
    "h1{color:#33d17a;font-size:20px;margin:0 0 4px}"
    "h2{color:#7cc4ff;font-size:15px;margin:26px 0 8px;border-bottom:1px solid #1e2a3a;"
    "padding-bottom:4px}"
    "h3{color:#c7d2e0;font-size:13px;margin:16px 0 6px}"
    ".sub{color:#5b6b80;font-size:11px}"
    "table{border-collapse:collapse;margin:8px 0;font-size:12px;width:100%}"
    "td,th{border:1px solid #1e2a3a;padding:5px 9px;text-align:left}"
    "th{background:#111722;color:#9fb2c9}"
    "td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}"
    "code{color:#f0b429}"
    ".chips span{display:inline-block;border:1px solid #29405a;border-radius:3px;"
    "padding:1px 6px;margin:2px 4px 2px 0;color:#9fb2c9;font-size:11px}"
    ".win{color:#33d17a;font-weight:700}"
    ".grid{display:flex;flex-wrap:wrap;gap:18px}"
    ".card{border:1px solid #1e2a3a;border-radius:5px;padding:10px 14px;min-width:110px}"
    ".card .v{font-size:17px;color:#eaf2ff}.card .k{font-size:10px;color:#5b6b80}"
    "ul{margin:6px 0;padding-left:18px}li{margin:2px 0}"
    "svg{background:#0c121b;border:1px solid #1e2a3a;border-radius:4px}"
    "footer{margin-top:32px;color:#41506a;font-size:10px;border-top:1px solid #1e2a3a;"
    "padding-top:8px}"
    "@media print{body{background:#fff;color:#111}h1{color:#0a7d3a}svg{background:#f4f6f8}}"
    "</style>"
)

_ASSUMPTIONS = [
    "All RF, emitters, threats and library entries are synthetic; no real, "
    "operational or captured signal data is used.",
    "The receiver observes one band per dwell; retune and dwell costs follow the "
    "fixed reward table in docs/REFERENCE.md I.5.",
    "Ground-truth metrics assume the simulator's occupancy_truth matrix; live "
    "metrics assume only receiver observations.",
    "Simulated EW effects modify the observed spectrum only, never "
    "occupancy_truth, so detection-under-jamming stays measurable.",
    "Scheduler-vs-baseline figures reconstruct the scenario from session "
    "metadata and re-run it; they are not a replay of the recorded steps.",
]
_LIMITATIONS = [
    "Single-run sessions carry no confidence interval; use the benchmark / "
    "ablation runners or a Monte Carlo sweep for CI-backed claims.",
    "Propagation, fading and PRI models are first-order and seeded, not a "
    "high-fidelity channel simulation.",
    "Classification and library matching are trained on synthetic data; accuracy "
    "on real signals is out of scope for this platform.",
    "DF error ellipses assume the configured node geometry and timing/bearing "
    "noise model; real multipath is not modelled.",
    "Live-mode metrics are proxy measures with no ground-truth validation.",
]


def _esc(v: object) -> str:
    return html.escape(str(v), quote=True)


def _or_dash(v: object) -> str:
    return _esc(v) if v not in (None, "", []) else _DASH


def _svg_line(
    values: list[float], *, w: int = 460, h: int = 90, pad: int = 6,
    stroke: str = "#33d17a", label: str = "",
) -> str:
    """Hand-built sparkline SVG (no external assets)."""
    if not values:
        return f"<svg width='{w}' height='{h}' role='img' aria-label='no data'></svg>"
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    n = len(values)
    step = (w - 2 * pad) / max(1, n - 1)
    pts = " ".join(
        f"{pad + i * step:.1f},{h - pad - (v - lo) / span * (h - 2 * pad):.1f}"
        for i, v in enumerate(values)
    )
    zline = ""
    if lo < 0 < hi:
        zy = h - pad - (0 - lo) / span * (h - 2 * pad)
        zline = (
            f"<line x1='{pad}' y1='{zy:.1f}' x2='{w - pad}' y2='{zy:.1f}' "
            f"stroke='#29405a' stroke-dasharray='3 3'/>"
        )
    caption = f"{_esc(label)} [{lo:.2f} .. {hi:.2f}]"
    return (
        f"<svg width='{w}' height='{h}' role='img' aria-label='{_esc(label)}'>"
        f"{zline}<polyline fill='none' stroke='{stroke}' stroke-width='1.5' "
        f"points='{pts}'/>"
        f"<text x='{pad}' y='12' fill='#5b6b80' font-size='10'>{caption}</text></svg>"
    )


def _svg_bars(
    pairs: list[tuple[str, float]], *, w: int = 460, h: int = 130, pad: int = 22,
    color: str = "#7cc4ff",
) -> str:
    if not pairs:
        return f"<svg width='{w}' height='{h}'></svg>"
    vals = [v for _, v in pairs]
    lo = min(0.0, min(vals))
    hi = max(0.0, max(vals)) or 1.0
    span = (hi - lo) or 1.0
    n = len(pairs)
    gap = (w - 2 * pad) / n
    bw = gap * 0.6
    base_y = h - pad - (0 - lo) / span * (h - 2 * pad)
    bars = []
    for i, (name, v) in enumerate(pairs):
        x = pad + i * gap + (gap - bw) / 2
        vy = h - pad - (v - lo) / span * (h - 2 * pad)
        top = min(vy, base_y)
        bh = abs(vy - base_y) or 1.0
        cx = x + bw / 2
        bars.append(
            f"<rect x='{x:.1f}' y='{top:.1f}' width='{bw:.1f}' height='{bh:.1f}' "
            f"fill='{color}'/>"
            f"<text x='{cx:.1f}' y='{h - 6}' fill='#5b6b80' font-size='9' "
            f"text-anchor='middle'>{_esc(name[:10])}</text>"
            f"<text x='{cx:.1f}' y='{top - 3:.1f}' fill='#9fb2c9' font-size='9' "
            f"text-anchor='middle'>{v:.2f}</text>"
        )
    return (
        f"<svg width='{w}' height='{h}' role='img' aria-label='metric bars'>"
        f"<line x1='{pad}' y1='{base_y:.1f}' x2='{w - pad}' y2='{base_y:.1f}' "
        f"stroke='#29405a'/>" + "".join(bars) + "</svg>"
    )


def _baseline_table(
    meta: dict, seeds: tuple[int, ...] = (0, 101, 202), steps: int = 300
) -> dict | None:
    """Re-run the scenario: round_robin vs the session scheduler, mean +/- CI."""
    from .simulation.engine import Simulation
    from .simulation.presets import get_preset, preset_names

    scenario = (meta.get("scenario") or "").strip()
    session_sched = (meta.get("scheduler") or "").strip() or "priority"
    if scenario not in preset_names():
        return None

    schedulers = ["round_robin"]
    if session_sched not in schedulers:
        schedulers.append(session_sched)

    env_base, rcv = get_preset(scenario)
    rows = []
    for name in schedulers:
        ar: list[float] = []
        ir: list[float] = []
        hp: list[float] = []
        for s in seeds:
            env = env_base.model_copy(update={"seed": env_base.seed + s})
            sim = Simulation(env_config=env, receiver_config=rcv, scheduler_name=name)
            sim.run(steps)
            m = sim.metrics_snapshot().model_dump()
            ar.append(m["average_reward"])
            ir.append(m["interception_ratio"])
            hp.append(m["high_priority_detection_rate"])

        def _agg(v: list[float]) -> dict:
            mean = statistics.fmean(v)
            ci = 1.96 * statistics.stdev(v) / (len(v) ** 0.5) if len(v) > 1 else 0.0
            return {"mean": round(mean, 4), "ci95": round(ci, 4)}

        rows.append(
            {
                "scheduler": name,
                "average_reward": _agg(ar),
                "interception_ratio": _agg(ir),
                "high_priority_detection_rate": _agg(hp),
            }
        )

    best = max(rows, key=lambda r: r["average_reward"]["mean"])
    delta = None
    if len(rows) == 2:
        delta = {
            k: round(rows[1][k]["mean"] - rows[0][k]["mean"], 4)
            for k in (
                "average_reward",
                "interception_ratio",
                "high_priority_detection_rate",
            )
        }
    return {
        "scenario": scenario,
        "seeds": [env_base.seed + s for s in seeds],
        "steps": steps,
        "rows": rows,
        "winner": best["scheduler"],
        "adaptive_minus_baseline": delta,
    }


def build_mission_report(session_id: str, *, with_baseline: bool = True) -> dict:
    """Assemble the mission-report dict for one persisted session."""
    from .store.sessions import get_session_store

    store = get_session_store()
    meta = store.meta(session_id)  # raises KeyError if missing

    decisions = store.data(session_id, "decisions")
    metric_rows = store.data(session_id, "metrics")
    alerts = store.data(session_id, "alerts")
    tracks = store.data(session_id, "tracks")
    df_fixes = store.data(session_id, "df_fixes")

    final_metrics = metric_rows[-1] if metric_rows else {}

    def _block(names: dict[str, str]) -> list[dict]:
        out = []
        for key, definition in names.items():
            if final_metrics.get(key) is not None:
                out.append(
                    {"name": key, "value": final_metrics[key], "definition": definition}
                )
        return out

    tl = []
    if decisions:
        n = len(decisions)
        idx = sorted({int(i * (n - 1) / 23) for i in range(min(24, n))})
        for i in idx:
            d = decisions[i]
            tl.append(
                {
                    "time_slot": d.get("time_slot"),
                    "selected_band": d.get("selected_band"),
                    "detected": bool(d.get("detected")),
                    "false_alarm": bool(d.get("false_alarm")),
                    "reward": d.get("reward"),
                }
            )

    reward_series = [r["average_reward"] for r in metric_rows if "average_reward" in r]

    def _latest_group(rows: list[dict]) -> list[dict]:
        if not rows:
            return []
        if any("time_slot" in r for r in rows):
            last_t = max(r.get("time_slot", -1) for r in rows)
            return [r for r in rows if r.get("time_slot", -1) == last_t]
        return rows

    tracks_final = _latest_group(tracks)
    df_final = _latest_group(df_fixes)
    ceps = [r["cep_km"] for r in df_final if isinstance(r.get("cep_km"), (int, float))]

    alert_states: dict[str, int] = {}
    alert_sev: dict[str, int] = {}
    for a in alerts:
        st = a.get("state", "?")
        sv = a.get("severity", "?")
        alert_states[st] = alert_states.get(st, 0) + 1
        alert_sev[sv] = alert_sev.get(sv, 0) + 1

    baseline = _baseline_table(meta) if with_baseline else None
    total_reward = sum(d.get("reward", 0.0) for d in decisions)

    return {
        "product": "SPECTRA-SCAN AI",
        "kind": "mission_report",
        "schema_version": meta.get("schema_version"),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "session": {
            "session_id": session_id,
            "name": meta.get("name"),
            "tags": meta.get("tags", []),
            "mode": meta.get("mode", ""),
            "scenario": meta.get("scenario", ""),
            "scheduler": meta.get("scheduler", ""),
            "started_at": meta.get("started_at"),
            "finished_at": meta.get("finished_at"),
            "row_counts": meta.get("row_counts", {}),
        },
        "summary": {
            "steps": len(decisions),
            "detections": sum(1 for d in decisions if d.get("detected")),
            "false_alarms": sum(1 for d in decisions if d.get("false_alarm")),
            "total_reward": round(total_reward, 2),
            "average_reward": round(total_reward / len(decisions), 4) if decisions else 0.0,
        },
        "metrics": {
            "mode_applicability": "ground_truth"
            if meta.get("mode") != "live_es"
            else "proxy",
            "simulation": _block(SIM_METRICS),
            "live": _block(LIVE_METRICS),
        },
        "timeline": tl,
        "reward_series": reward_series,
        "scheduler_vs_baseline": baseline,
        "tracks": tracks_final,
        "df_fixes": {
            "fixes": df_final,
            "mean_cep_km": round(statistics.fmean(ceps), 3) if ceps else None,
            "n": len(df_final),
        },
        "alerts": {
            "total": len(alerts),
            "by_state": alert_states,
            "by_severity": alert_sev,
            "items": alerts[:50],
        },
        "assumptions": _ASSUMPTIONS,
        "limitations": _LIMITATIONS,
    }


def mission_report_to_html(report: dict) -> str:
    s = report["session"]
    summ = report["summary"]
    p: list[str] = [
        "<!doctype html><meta charset='utf-8'>",
        f"<title>SPECTRA-SCAN mission report {_esc(s['session_id'])}</title>",
        _MISSION_STYLE,
        "<h1>SPECTRA-SCAN AI &mdash; Mission Report</h1>",
        f"<div class='sub'>session <code>{_esc(s['session_id'])}</code> &middot; "
        f"generated {_esc(report['generated_at'])} &middot; schema "
        f"v{_esc(report['schema_version'])} &middot; "
        f"synthetic / receive-only / simulation-only</div>",
    ]

    # 1. summary
    p.append("<h2>1. Session summary</h2><div class='chips'>")
    for k in ("name", "mode", "scenario", "scheduler", "started_at", "finished_at"):
        p.append(f"<span>{_esc(k)}: {_or_dash(s.get(k))}</span>")
    for tag in s.get("tags", []):
        p.append(f"<span>#{_esc(tag)}</span>")
    p.append("</div><div class='grid' style='margin-top:8px'>")
    for k, v in (
        ("steps", summ["steps"]),
        ("detections", summ["detections"]),
        ("false alarms", summ["false_alarms"]),
        ("total reward", summ["total_reward"]),
        ("avg reward", summ["average_reward"]),
    ):
        p.append(
            f"<div class='card'><div class='v'>{_esc(v)}</div>"
            f"<div class='k'>{_esc(k)}</div></div>"
        )
    p.append("</div>")

    # 2. metric split
    p.append(f"<h2>2. Metrics &mdash; {_esc(report['metrics']['mode_applicability'])}</h2>")
    for title, block in (
        ("Simulation metrics (need ground truth)", report["metrics"]["simulation"]),
        ("Live metrics (no ground truth)", report["metrics"]["live"]),
    ):
        p.append(f"<h3>{_esc(title)}</h3>")
        if not block:
            p.append("<div class='sub'>not recorded for this session</div>")
            continue
        p.append(
            "<table><tr><th>metric</th><th class='n'>value</th><th>definition</th></tr>"
        )
        for row in block:
            p.append(
                f"<tr><td><code>{_esc(row['name'])}</code></td>"
                f"<td class='n'>{_esc(row['value'])}</td>"
                f"<td>{_esc(row['definition'])}</td></tr>"
            )
        p.append("</table>")
    if report["metrics"]["simulation"]:
        pairs = [
            (r["name"].replace("_", " "), float(r["value"]))
            for r in report["metrics"]["simulation"]
            if isinstance(r["value"], (int, float)) and abs(float(r["value"])) <= 5
        ][:6]
        p.append(_svg_bars(pairs))

    # 3. reward over time
    p.append("<h2>3. Reward over the session</h2>")
    p.append(_svg_line(report["reward_series"], label="average_reward"))

    # 4. scheduler vs baseline
    p.append("<h2>4. Scheduler vs baseline</h2>")
    b = report["scheduler_vs_baseline"]
    if not b:
        p.append(
            "<div class='sub'>scenario not reconstructible from session metadata "
            "&mdash; run Strategy Comparison / Monte Carlo for a CI-backed table.</div>"
        )
    else:
        p.append(
            f"<div class='sub'>scenario <code>{_esc(b['scenario'])}</code> &middot; "
            f"seeds {_esc(b['seeds'])} &middot; {b['steps']} steps/seed &middot; "
            f"winner <span class='win'>{_esc(b['winner'])}</span></div>"
        )
        p.append(
            "<table><tr><th>scheduler</th><th class='n'>avg reward</th>"
            "<th class='n'>interception</th><th class='n'>hi-pri det.</th></tr>"
        )
        for r in b["rows"]:
            cls = " class='win'" if r["scheduler"] == b["winner"] else ""
            ar = r["average_reward"]
            ir = r["interception_ratio"]
            hp = r["high_priority_detection_rate"]
            p.append(
                f"<tr{cls}><td>{_esc(r['scheduler'])}</td>"
                f"<td class='n'>{ar['mean']:.3f} &plusmn;{ar['ci95']:.2f}</td>"
                f"<td class='n'>{ir['mean']:.3f} &plusmn;{ir['ci95']:.3f}</td>"
                f"<td class='n'>{hp['mean']:.3f} &plusmn;{hp['ci95']:.3f}</td></tr>"
            )
        p.append("</table>")
        d = b["adaptive_minus_baseline"]
        if d:
            p.append(
                "<div class='sub'>adaptive minus baseline: avg reward "
                f"<b>{d['average_reward']:+.3f}</b>, interception "
                f"<b>{d['interception_ratio']:+.3f}</b>, hi-pri detection "
                f"<b>{d['high_priority_detection_rate']:+.3f}</b></div>"
            )

    # 5. timeline
    p.append("<h2>5. Decision timeline (sampled)</h2>")
    if report["timeline"]:
        p.append(
            "<table><tr><th class='n'>t</th><th class='n'>band</th><th>outcome</th>"
            "<th class='n'>reward</th></tr>"
        )
        for row in report["timeline"]:
            out = (
                "false alarm"
                if row["false_alarm"]
                else "detection"
                if row["detected"]
                else "empty"
            )
            p.append(
                f"<tr><td class='n'>{_esc(row['time_slot'])}</td>"
                f"<td class='n'>{_esc(row['selected_band'])}</td>"
                f"<td>{out}</td><td class='n'>{_esc(row['reward'])}</td></tr>"
            )
        p.append("</table>")
    else:
        p.append("<div class='sub'>no decisions recorded</div>")

    # 6. tracks
    p.append("<h2>6. Tracks &amp; classification</h2>")
    if report["tracks"]:
        p.append(
            "<table><tr><th>track</th><th>class</th><th class='n'>conf</th>"
            "<th>library match</th><th class='n'>threat</th></tr>"
        )
        for t in report["tracks"][:40]:
            cls = t.get("modulation_class") or t.get("class")
            p.append(
                f"<tr><td>{_or_dash(t.get('track_id'))}</td>"
                f"<td>{_or_dash(cls)}</td>"
                f"<td class='n'>{_or_dash(t.get('confidence'))}</td>"
                f"<td>{_or_dash(t.get('library_match'))}</td>"
                f"<td class='n'>{_or_dash(t.get('threat'))}</td></tr>"
            )
        p.append("</table>")
    else:
        p.append("<div class='sub'>no track snapshot captured for this session</div>")

    # 7. DF
    df = report["df_fixes"]
    p.append("<h2>7. Direction finding</h2>")
    if df["fixes"]:
        p.append(
            f"<div class='sub'>{df['n']} fixes &middot; mean CEP "
            f"{_esc(df['mean_cep_km'])} km</div>"
        )
    else:
        p.append("<div class='sub'>no DF fixes captured for this session</div>")

    # 8. alerts
    al = report["alerts"]
    p.append("<h2>8. Alerts</h2>")
    p.append(
        f"<div class='sub'>{al['total']} total &middot; by state "
        f"{_esc(al['by_state'])} &middot; by severity {_esc(al['by_severity'])}</div>"
    )

    # 9 / 10
    p.append("<h2>9. Assumptions</h2><ul>")
    p += [f"<li>{_esc(a)}</li>" for a in report["assumptions"]]
    p.append("</ul><h2>10. Limitations</h2><ul>")
    p += [f"<li>{_esc(x)}</li>" for x in report["limitations"]]
    p.append("</ul>")

    p.append(
        "<footer>SPECTRA-SCAN AI mission report &middot; all data synthetic &middot; "
        "hardware path receive-only &middot; EW effects simulation-only &middot; "
        "no transmit capability &middot; generated fully offline.</footer>"
    )
    return "".join(p)
