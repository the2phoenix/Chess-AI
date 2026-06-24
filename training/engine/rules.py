"""Game-ending rules — one place so search, self-play, and the viewer agree.

python-chess knows the FIDE draw rules; this module wraps them with the project's
vocabulary and one deliberate **house rule** about repetition.

House rule (intentionally NOT standard FIDE): repeating a position is a draw
ONLY when the repeated cycle involved checks — i.e. a *perpetual check*. Plain
repetition of ordinary (non-checking) moves does **not** end the game; the
engine simply plays on. The no-progress fifty/seventyfive-move rules remain as a
backstop so a purely shuffling game still terminates eventually.
"""

from __future__ import annotations

import chess


def is_threefold_repetition(board: chess.Board) -> bool:
    """True if the current position has occurred three times (a draw).

    A position can only repeat across reversible moves, so the halfmove clock
    must be at least 8 for three occurrences — we check that first to skip the
    (relatively expensive) repetition scan in the vast majority of positions.
    """
    return board.halfmove_clock >= 8 and board.is_repetition(3)


def is_perpetual_check(board: chess.Board, lookback: int = 8) -> bool:
    """A threefold repetition whose repeating cycle contained checks.

    This is the "in check, same moves repeated three times → draw" case: a side
    that can't make progress keeps checking, the other keeps escaping, the
    position cycles, and it's drawn.
    """
    if not is_threefold_repetition(board):
        return False
    return _checks_in_recent_history(board, lookback) > 0


def is_draw(board: chess.Board) -> bool:
    """Any draw under this project's house rules.

    Repetition draws ONLY as a perpetual *check* (see module docstring); plain
    repetition does not. The no-progress fifty/seventyfive-move rules still apply
    so a shuffling game can't run forever.
    """
    return (
        board.is_stalemate()
        or board.is_insufficient_material()
        or is_perpetual_check(board)
        or board.is_seventyfive_moves()
        or board.is_fifty_moves()
    )


def is_game_over(board: chess.Board) -> bool:
    """Checkmate, or any draw under the house rules (see :func:`is_draw`)."""
    return board.is_checkmate() or is_draw(board)


def game_result(board: chess.Board) -> str:
    """Result string under the house rules: '1-0' | '0-1' | '1/2-1/2' | '*'.

    Use this instead of ``board.result(claim_draw=True)`` so the project's
    repetition house rule (perpetual-check-only) is honoured consistently.
    """
    if board.is_checkmate():
        return "0-1" if board.turn == chess.WHITE else "1-0"
    if is_draw(board):
        return "1/2-1/2"
    return "*"


def describe_termination(board: chess.Board) -> str | None:
    """Human-readable reason the game ended, or ``None`` if it hasn't."""
    if board.is_checkmate():
        return "checkmate"
    if board.is_stalemate():
        return "stalemate"
    if board.is_insufficient_material():
        return "insufficient material"
    if is_perpetual_check(board):
        return "perpetual check"
    # Plain threefold/fivefold repetition is intentionally NOT a draw here.
    if board.is_seventyfive_moves() or board.is_fifty_moves():
        return "fifty-move rule"
    return None


def _checks_in_recent_history(board: chess.Board, plies: int) -> int:
    """Count how many of the last ``plies`` positions were checks.

    Walks back over a copy so the caller's board is untouched.
    """
    probe = board.copy(stack=plies)
    count = 0
    for _ in range(min(plies, len(probe.move_stack))):
        if probe.is_check():
            count += 1
        probe.pop()
    return count
