"""Receiver-node registry (Extension Step 5).

Single source of truth for the DF node layout: populated from a loaded
scenario, replaced by an operator via ``POST /api/df/nodes``, or extended by a
LAN peer via ``POST /api/df/register``.
"""

from __future__ import annotations

import threading
import uuid

import numpy as np

from ..models.core import ReceiverNode


def default_layout(spread_km: float = 40.0, n: int = 4) -> list[ReceiverNode]:
    """A ring of ``n`` synced nodes around the origin."""
    spread_km = max(spread_km, 5.0)
    nodes: list[ReceiverNode] = []
    for i in range(n):
        ang = 2.0 * np.pi * i / n + np.pi / 4.0
        nodes.append(
            ReceiverNode(
                node_id=f"node-{i + 1}",
                name=f"Node {i + 1}",
                x_km=round(float(spread_km * np.cos(ang)), 3),
                y_km=round(float(spread_km * np.sin(ang)), 3),
                sync_source="gpsdo",
                sync_quality=0.95,
                timing_error_ns=20.0,
                bearing_error_deg=3.0,
                kind="sim",
                healthy=True,
            )
        )
    return nodes


class NodeRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._nodes: dict[str, ReceiverNode] = {}
        self.set_nodes(default_layout())

    def set_nodes(self, nodes: list[ReceiverNode]) -> list[ReceiverNode]:
        with self._lock:
            self._nodes = {}
            for i, n in enumerate(nodes):
                n = n.model_copy(deep=True)
                if not n.node_id:
                    n.node_id = f"node-{uuid.uuid4().hex[:6]}"
                if not n.name:
                    n.name = n.node_id
                self._nodes[n.node_id] = n
            return self.get_nodes()

    def get_nodes(self) -> list[ReceiverNode]:
        with self._lock:
            return [n.model_copy(deep=True) for n in self._nodes.values()]

    def register(self, node: ReceiverNode) -> ReceiverNode:
        with self._lock:
            node = node.model_copy(deep=True)
            if not node.node_id:
                node.node_id = f"lan-{uuid.uuid4().hex[:6]}"
            node.kind = "lan"
            self._nodes[node.node_id] = node
            return node.model_copy(deep=True)

    def count(self) -> int:
        with self._lock:
            return len(self._nodes)


_registry: NodeRegistry | None = None


def get_node_registry() -> NodeRegistry:
    global _registry
    if _registry is None:
        _registry = NodeRegistry()
    return _registry


def _reset_for_tests() -> None:
    global _registry
    _registry = None
