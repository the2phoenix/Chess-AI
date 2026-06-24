"""I/O helpers: turning games into the language-agnostic artifacts the rest of
the project consumes (PGN for games, JSON for weights).

Kept small in Phase 1 — just enough to record a self-play game as PGN so it can
be inspected or, later, replayed in the frontend.
"""

from .pgn import game_to_pgn, save_pgn

__all__ = ["game_to_pgn", "save_pgn"]
