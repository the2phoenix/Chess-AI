"""The Engine — a thin, friendly wrapper over search + evaluation.

An ``Engine`` is defined by its **genome** (the evaluation weights) plus a
search budget (depth and/or time). This is the unit the Phase 2 GA will create
populations of: same search, different genomes.
"""

from __future__ import annotations

import random

import chess

from .evaluation import Genome, DEFAULT_GENOME, evaluate
from .search import search, SearchResult, MATE_THRESHOLD, MATE_SCORE
from .rules import is_game_over


class Engine:
    """A self-contained chess-playing agent.

    Parameters
    ----------
    genome:
        Evaluation weights. Defaults to the hand-tuned :data:`DEFAULT_GENOME`.
    depth:
        Maximum search depth (plies). Use 2–3 for fast self-play, deeper for
        showcase/analysis.
    time_limit:
        Optional per-move time budget in seconds. When set, search uses
        iterative deepening and stops on the budget, returning the best move
        from the last completed depth.
    name:
        Optional label, handy for tournaments and logs (e.g. "Gen-1").
    """

    def __init__(
        self,
        genome: Genome | None = None,
        depth: int = 3,
        time_limit: float | None = None,
        name: str = "Engine",
        random_margin: int = 0,
    ) -> None:
        self.genome = genome if genome is not None else DEFAULT_GENOME
        self.depth = depth
        self.time_limit = time_limit
        self.name = name
        # > 0 adds move variety (pick among near-best); 0 = deterministic.
        self.random_margin = random_margin
        self._rng = random.Random()

    def select_move(self, board: chess.Board) -> chess.Move | None:
        """Return the engine's chosen move for the current position.

        Returns ``None`` only if the game is already over (house rules: plain
        repetition is not game-over; see :mod:`engine.rules`).
        """
        if is_game_over(board):
            return None
        result = self.analyse(board)
        return result.move

    def analyse(self, board: chess.Board) -> SearchResult:
        """Run the search and return the full :class:`SearchResult`."""
        return search(
            board,
            depth=self.depth,
            genome=self.genome,
            time_limit=self.time_limit,
            random_margin=self.random_margin,
            rng=self._rng,
        )

    def evaluate(self, board: chess.Board) -> int:
        """Static evaluation of ``board`` (White's perspective, centipawns)."""
        return evaluate(board, self.genome)

    def eval_bar_score(self, board: chess.Board) -> int:
        """Search-backed score for the showcase eval bar (White's perspective).

        The frontend renders this as the bar. It's the engine's own opinion, so
        we negate the side-to-move score from search back to White's view.
        """
        result = self.analyse(board)
        score = result.score
        # Convert mate-distance scores into a large clamped value.
        if score > MATE_THRESHOLD:
            score = MATE_SCORE
        elif score < -MATE_THRESHOLD:
            score = -MATE_SCORE
        # search() scores from the side to move; flip to White's perspective.
        return score if board.turn == chess.WHITE else -score

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"Engine(name={self.name!r}, depth={self.depth}, time_limit={self.time_limit})"
