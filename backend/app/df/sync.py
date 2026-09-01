"""Clock-sync quality -> effective timing uncertainty.

Poorer sync (lower quality, weaker source) inflates the 1-sigma timing error,
which propagates through the TDOA solver into a larger error ellipse.
"""

from __future__ import annotations

_SOURCE_FLOOR_NS = {"gpsdo": 15.0, "ptp": 40.0, "none": 400.0}


def effective_timing_sigma_ns(node) -> float:
    base = max(float(node.timing_error_ns), _SOURCE_FLOOR_NS.get(node.sync_source, 400.0))
    q = max(float(node.sync_quality), 0.05)
    return base / q


def effective_timing_sigma_s(node) -> float:
    return effective_timing_sigma_ns(node) * 1e-9


def sync_dashboard(nodes: list) -> list[dict]:
    rows = []
    for n in nodes:
        rows.append(
            {
                "node_id": n.node_id,
                "name": n.name,
                "sync_source": n.sync_source,
                "sync_quality": round(float(n.sync_quality), 3),
                "timing_sigma_ns": round(effective_timing_sigma_ns(n), 1),
                "bearing_error_deg": round(float(n.bearing_error_deg), 2),
                "healthy": bool(n.healthy),
                "last_seen_slot": int(n.last_seen_slot),
                "kind": n.kind,
                "x_km": round(float(n.x_km), 3),
                "y_km": round(float(n.y_km), 3),
            }
        )
    return rows
