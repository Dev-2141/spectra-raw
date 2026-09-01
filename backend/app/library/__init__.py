"""Synthetic emitter/threat library (Extension Step 4).

SQLite-backed, versioned. Every entry carries ``synthetic: true``. Never holds
real or classified emitter data.
"""

from .store import EmitterLibrary, get_library, match_features

__all__ = ["EmitterLibrary", "get_library", "match_features"]
