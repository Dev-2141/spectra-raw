"""FastAPI routing layer."""

from .routes import router
from .manager import SimulationManager, get_manager

__all__ = ["router", "SimulationManager", "get_manager"]
