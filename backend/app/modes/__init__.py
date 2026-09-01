"""Platform mode context: ``simulation`` vs ``live_es``.

The mode is owned by the process, referenced by the simulation manager, and
switched only through ``POST /api/mode`` (operator+, confirmed, audited). Boot
mode is always ``simulation`` — the safe default.
"""

from .manager import MODES, ModeManager, get_mode_manager

__all__ = ["MODES", "ModeManager", "get_mode_manager"]
