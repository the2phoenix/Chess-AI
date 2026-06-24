"""PGN export. JSON for weights, PGN for games — so Python writes and JS reads.

These helpers wrap python-chess's PGN support with the tags this project cares
about (the two engines and the game mode), and write to disk.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import chess
import chess.pgn


def game_to_pgn(
    board: chess.Board,
    white_name: str = "White",
    black_name: str = "Black",
    mode: str = "ai_vs_ai",
    event: str = "Darwin's Gambit self-play",
) -> chess.pgn.Game:
    """Build a :class:`chess.pgn.Game` from a *finished* (or partial) board.

    The board carries its move stack, so we replay it into a PGN game with the
    standard seven-tag roster plus a ``Mode`` tag matching the Supabase schema
    (``ai_vs_ai | vs_trained | vs_adaptive``).
    """
    game = chess.pgn.Game.from_board(board)
    game.headers["Event"] = event
    game.headers["Site"] = "Darwin's Gambit"
    game.headers["Date"] = _dt.date.today().strftime("%Y.%m.%d")
    game.headers["White"] = white_name
    game.headers["Black"] = black_name
    game.headers["Result"] = board.result(claim_draw=True)
    game.headers["Mode"] = mode
    return game


def save_pgn(game: chess.pgn.Game, path: str | Path) -> Path:
    """Write a PGN game to ``path`` (creating parent dirs). Returns the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        print(game, file=fh, end="\n")
    return path
