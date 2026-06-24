"""Per-user adaptive opponent (Phase 7 / Mode F3).

A fixed strong base engine plus a small per-user layer that learns *this*
player's habits and exploits them — kept deliberately separate from the
evolution pipeline (PROJECT_GUIDE.md guardrail) so neither contaminates the other.

- ``model``    : :class:`OpponentModel` — the per-user habit/mistake profile.
- ``adaptive`` : :class:`AdaptiveEngine` — base engine + exploit layer.
"""

from .model import OpponentModel, position_key, BLUNDER_DROP_CP, WARMUP_GAMES
from .adaptive import AdaptiveEngine

__all__ = [
    "OpponentModel",
    "AdaptiveEngine",
    "position_key",
    "BLUNDER_DROP_CP",
    "WARMUP_GAMES",
]
