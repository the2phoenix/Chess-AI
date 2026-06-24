"""Search — minimax with alpha-beta pruning (Phase 1 MVP).

This is the *fixed* half of the engine: it never evolves. It decides which
moves to explore; the evolved :mod:`evaluation` decides how good leaf positions
are.

Design notes (matching docs/GSD.md):
- **Negamax** formulation of minimax: one code path, scores always from the
  side-to-move's perspective, the parent negates the child.
- **Alpha-beta pruning** skips branches that cannot affect the result.
- **Iterative deepening**: search depth 1, 2, 3 … keeping the best move so far.
  This is what lets showcase/clock play stop on a time budget; during evolution
  we just call a fixed shallow depth (2–3).
- **Mate scoring**: checkmate is a large value, adjusted by ply so the engine
  prefers mating sooner and delaying being mated.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

import chess

from .evaluation import Genome, DEFAULT_GENOME, evaluate, PIECE_VALUES
from .nn_eval import NNGenome, nn_evaluate
from .rules import is_perpetual_check

# A score this large means "mate". We keep it well below the static-eval
# sentinels so arithmetic on it never overflows into nonsense.
MATE_SCORE = 1_000_000
# Anything within this margin of MATE_SCORE is "a mate in N", not a real eval.
MATE_THRESHOLD = MATE_SCORE - 1000


@dataclass
class SearchResult:
    """Outcome of a search: the chosen move and why."""

    move: chess.Move | None
    score: int          # centipawns, from the side-to-move's perspective
    depth: int          # depth actually completed
    nodes: int          # nodes visited (for diagnostics)


def search(
    board: chess.Board,
    depth: int = 3,
    genome: Genome = DEFAULT_GENOME,
    time_limit: float | None = None,
    random_margin: int = 0,
    rng: random.Random | None = None,
) -> SearchResult:
    """Find the best move for the side to move.

    Uses iterative deepening up to ``depth``. If ``time_limit`` (seconds) is
    given, deepening stops once the budget is spent and the best move from the
    last *completed* depth is returned — never a half-searched one.

    ``random_margin`` adds *variety*: when > 0, the root picks uniformly at
    random among moves scoring within ``random_margin`` centipawns of the best,
    so repeated games differ without playing weak moves (forced mates/tactics,
    being far above the margin, are still chosen). Default 0 = fully
    deterministic (used by the GA, which needs reproducible fitness).
    """
    deadline = (time.monotonic() + time_limit) if time_limit else None
    if random_margin > 0 and rng is None:
        rng = random.Random()

    best = SearchResult(move=None, score=0, depth=0, nodes=0)
    total_nodes = 0
    # The recursion mutates ``board`` via push/pop. A timeout can fire mid-line,
    # so remember the starting stack depth and restore it if we bail out — the
    # caller's board must come back exactly as it went in.
    baseline_ply = len(board.move_stack)

    for current_depth in range(1, max(1, depth) + 1):
        counter = _NodeCounter()
        try:
            if random_margin > 0:
                move, score = _search_root_varied(
                    board, current_depth, genome, deadline, counter, rng, random_margin
                )
            else:
                move, score = _search_root(board, current_depth, genome, deadline, counter)
        except _Timeout:
            while len(board.move_stack) > baseline_ply:
                board.pop()
            total_nodes += counter.nodes
            break

        total_nodes += counter.nodes
        best = SearchResult(
            move=move, score=score, depth=current_depth, nodes=total_nodes
        )

        # Found a forced mate — no point searching deeper.
        if abs(score) > MATE_THRESHOLD:
            break
        if deadline is not None and time.monotonic() >= deadline:
            break

    return best


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
class _NodeCounter:
    __slots__ = ("nodes",)

    def __init__(self) -> None:
        self.nodes = 0


class _Timeout(Exception):
    """Raised internally to abort a search that ran past its deadline."""


def _search_root(
    board: chess.Board,
    depth: int,
    genome: Genome,
    deadline: float | None,
    counter: _NodeCounter,
) -> tuple[chess.Move | None, int]:
    alpha, beta = -MATE_SCORE, MATE_SCORE
    best_move: chess.Move | None = None
    best_score = -MATE_SCORE

    for move in _ordered_moves(board):
        board.push(move)
        score = -_negamax(board, depth - 1, -beta, -alpha, genome, deadline, counter)
        board.pop()

        if score > best_score:
            best_score = score
            best_move = move
        if best_score > alpha:
            alpha = best_score

    return best_move, best_score


def _search_root_varied(
    board: chess.Board,
    depth: int,
    genome: Genome,
    deadline: float | None,
    counter: _NodeCounter,
    rng: random.Random,
    margin: int,
) -> tuple[chess.Move | None, int]:
    """Score every root move with a full window, then pick randomly among the
    near-best (within ``margin`` cp). Full window (no root pruning) so the
    near-best scores are exact — at the cost of not pruning the handful of root
    moves, which is cheap and only used in the viewer's variety mode."""
    scored: list[tuple[chess.Move, int]] = []
    for move in _ordered_moves(board):
        board.push(move)
        score = -_negamax(board, depth - 1, -MATE_SCORE, MATE_SCORE, genome, deadline, counter)
        board.pop()
        scored.append((move, score))

    if not scored:
        return None, 0
    best = max(score for _, score in scored)
    pool = [move for move, score in scored if score >= best - margin]
    return rng.choice(pool), best


def _negamax(
    board: chess.Board,
    depth: int,
    alpha: int,
    beta: int,
    genome: Genome,
    deadline: float | None,
    counter: _NodeCounter,
) -> int:
    counter.nodes += 1

    # Check the clock occasionally (cheap: every 2048 nodes).
    if deadline is not None and (counter.nodes & 2047) == 0:
        if time.monotonic() >= deadline:
            raise _Timeout

    # Terminal positions: mate is depth-adjusted so sooner mates score higher.
    if board.is_checkmate():
        return -MATE_SCORE + (board.ply())  # being mated is bad for us
    if (
        board.is_stalemate()
        or board.is_insufficient_material()
        or board.is_seventyfive_moves()
        # House rule: repetition is a draw ONLY when it's a perpetual check, so
        # the engine seeks a saving perpetual / avoids throwing a win away into
        # one — but it does NOT treat plain repetition as a draw.
        or is_perpetual_check(board)
    ):
        return 0

    if depth <= 0:
        return _evaluate_side_to_move(board, genome)

    best = -MATE_SCORE
    for move in _ordered_moves(board):
        board.push(move)
        score = -_negamax(board, depth - 1, -beta, -alpha, genome, deadline, counter)
        board.pop()

        if score > best:
            best = score
        if best > alpha:
            alpha = best
        if alpha >= beta:
            break  # beta cut-off: opponent won't allow this line

    return best


def _evaluate_side_to_move(board: chess.Board, genome) -> int:
    """Evaluation negated to the side-to-move's perspective (negamax needs this).

    Dispatches on genome type so the same search drives either the handcrafted
    scalar evaluation or the V2 neural-net evaluator — no other plumbing changes.
    """
    if isinstance(genome, NNGenome):
        white_score = nn_evaluate(board, genome)
    else:
        white_score = evaluate(board, genome)
    return white_score if board.turn == chess.WHITE else -white_score


def _ordered_moves(board: chess.Board):
    """Yield moves with captures first (MVV-LVA-ish) to improve alpha-beta cuts.

    Better move ordering means more cut-offs and a faster search, with no effect
    on the result. We score captures by victim value minus attacker value, and
    give checks a small bonus.
    """
    moves = list(board.legal_moves)

    def score(move: chess.Move) -> int:
        s = 0
        if board.is_capture(move):
            victim = board.piece_at(move.to_square)
            attacker = board.piece_at(move.from_square)
            # En-passant has no piece on the target square; treat as a pawn.
            victim_value = PIECE_VALUES[victim.piece_type] if victim else PIECE_VALUES[chess.PAWN]
            attacker_value = PIECE_VALUES[attacker.piece_type] if attacker else 0
            s += 10_000 + victim_value - attacker_value
        if move.promotion:
            s += PIECE_VALUES.get(move.promotion, 0)
        if board.gives_check(move):
            s += 50
        return s

    moves.sort(key=score, reverse=True)
    return moves
