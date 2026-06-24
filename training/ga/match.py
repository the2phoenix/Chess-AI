"""Play one game between two genomes and score it objectively.

Two engines with the same search but different genomes play a game. The result
feeds the GA's fitness. A game that hits the move cap is adjudicated by **raw
material balance** (fixed piece values) — deliberately *not* by either genome's
own evaluation, so a genome can't earn fitness just by liking its own position.
"""

from __future__ import annotations

from dataclasses import dataclass

import chess

from engine import Engine, Genome, describe_termination, evaluate, is_game_over, game_result
from engine.evaluation import PIECE_VALUES

# Score from White's perspective for each result string.
_SCORE = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}


@dataclass
class GameOutcome:
    score_white: float     # 1.0 win / 0.5 draw / 0.0 loss, from White's view
    result: str            # "1-0" | "0-1" | "1/2-1/2"
    plies: int
    termination: str
    board: chess.Board     # final position (for optional PGN export)


def play_match(
    white: Genome,
    black: Genome,
    depth: int = 2,
    max_plies: int = 160,
    adjudicate_margin: int = 200,
    opening: list[str] | None = None,
) -> GameOutcome:
    """Play White-genome vs Black-genome and return the outcome.

    ``opening`` is an optional list of UCI moves to start from (used to vary
    games for a robust strength benchmark); the engines play on from there.
    """
    we = Engine(genome=white, depth=depth, name="White")
    be = Engine(genome=black, depth=depth, name="Black")

    board = chess.Board()
    if opening:
        for uci in opening:
            board.push(chess.Move.from_uci(uci))

    while not is_game_over(board) and len(board.move_stack) < max_plies:
        engine = we if board.turn == chess.WHITE else be
        move = engine.select_move(board)
        if move is None:
            break
        board.push(move)

    return _outcome(board, adjudicate_margin)


def _outcome(board: chess.Board, margin: int) -> GameOutcome:
    plies = len(board.move_stack)
    if is_game_over(board):
        result = game_result(board)
        termination = describe_termination(board) or "game over"
    else:
        # Move cap reached: adjudicate by objective material balance.
        balance = _material_balance(board)
        if balance >= margin:
            result = "1-0"
        elif balance <= -margin:
            result = "0-1"
        else:
            result = "1/2-1/2"
        termination = "adjudicated (move cap)"
    return GameOutcome(_SCORE[result], result, plies, termination, board)


def trace_game(board: chess.Board) -> tuple[list[str], list[int]]:
    """Replay a finished game's move stack, capturing (FEN, White-eval) per ply.

    Returns ``(fens, evals)`` including the starting position, so the showcase
    can render each frame and an eval bar with no engine in the browser. Assumes
    the game started from the standard position (true for tournament games).
    """
    replay = chess.Board()
    fens = [replay.fen()]
    evals = [evaluate(replay)]
    for move in board.move_stack:
        replay.push(move)
        fens.append(replay.fen())
        evals.append(evaluate(replay))
    return fens, evals


def _material_balance(board: chess.Board) -> int:
    """White material minus Black material, in centipawns (genome-independent)."""
    balance = 0
    for piece in board.piece_map().values():
        value = PIECE_VALUES[piece.piece_type]
        balance += value if piece.color == chess.WHITE else -value
    return balance
