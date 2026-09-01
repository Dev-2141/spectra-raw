"""Receive-only hardware abstraction for the live path.

RECEIVE-ONLY BY CONSTRUCTION. ``HardwareAdapter`` exposes no transmit method,
and no module in this package may reference a transmit call. The exact list of
banned symbols lives in ``base.FORBIDDEN_TX_SYMBOLS``; ``test_ext_step2.py``
greps every adapter module against it.
"""

from .base import FORBIDDEN_TX_SYMBOLS, HardwareAdapter, HardwareUnavailable
from .manager import HardwareManager, get_hardware_manager

__all__ = [
    "FORBIDDEN_TX_SYMBOLS",
    "HardwareAdapter",
    "HardwareUnavailable",
    "HardwareManager",
    "get_hardware_manager",
]
