"""Multi-node direction finding / geolocation (Extension Step 5).

Receive-only. Three or more passive nodes contribute TOA (for TDOA) and/or
bearing (AOA) measurements; the solvers fuse them into a position estimate with
a 95% error ellipse. The same fusion code runs on simulated geometry and on
observations pushed by LAN peer nodes.
"""

from .nodes import NodeRegistry, default_layout, get_node_registry
from .solvers import ellipse_from_cov, fuse_estimates, solve_aoa, solve_tdoa

__all__ = [
    "NodeRegistry",
    "default_layout",
    "get_node_registry",
    "ellipse_from_cov",
    "fuse_estimates",
    "solve_aoa",
    "solve_tdoa",
]
