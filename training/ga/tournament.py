"""Tournaments: turn a population into fitness scores, in parallel.

Two jobs:

- :func:`round_robin` — every genome plays every other (both colours). The total
  score is the genome's **fitness** (used for selection). This is relative: it
  only ranks genomes *within* one generation.

- :func:`benchmark` — the best genome plays a fixed baseline (the hand-tuned
  ``DEFAULT_GENOME``) from a fixed set of openings. Its win-rate is an
  **absolute** strength number, comparable across generations — that's the curve
  the Phase 2 acceptance criterion asks to see rise.

Games are independent, so they fan out across processes (heavy compute, offline
only — never a web function). Worker functions are module-level so they pickle
cleanly under Windows ``spawn``.
"""

from __future__ import annotations

import multiprocessing as mp
import random

from engine import Genome, NNGenome

from .match import play_match, trace_game, _SCORE
from .lineage import GameRecord


def genome_kind(genome) -> str:
    """'nn' for the neural-net genome, else 'scalar'."""
    return "nn" if isinstance(genome, NNGenome) else "scalar"


def _make_genome(kind: str, vec):
    return NNGenome.from_vector(vec) if kind == "nn" else Genome.from_vector(vec)


# --------------------------------------------------------------------------- #
# Parallel worker (top-level + picklable).
# --------------------------------------------------------------------------- #
def _play_task(args: tuple) -> GameRecord:
    (white_id, white_vec, white_kind, black_id, black_vec, black_kind,
     depth, max_plies, opening, keep_pgn, log_moves) = args
    outcome = play_match(
        _make_genome(white_kind, white_vec),
        _make_genome(black_kind, black_vec),
        depth=depth,
        max_plies=max_plies,
        opening=opening,
    )
    pgn = None
    if keep_pgn:
        # Import lazily so the common (no-PGN) path stays light.
        from chess_io import game_to_pgn
        pgn = str(game_to_pgn(outcome.board, white_name=white_id, black_name=black_id))
    fens = evals = None
    if log_moves:
        fens, evals = trace_game(outcome.board)
    return GameRecord(
        white_id=white_id,
        black_id=black_id,
        result=outcome.result,
        plies=outcome.plies,
        termination=outcome.termination,
        pgn=pgn,
        fens=fens,
        evals=evals,
    )


def _run_tasks(tasks: list[tuple], processes: int | None) -> list[GameRecord]:
    if processes and processes > 1 and len(tasks) > 1:
        with mp.Pool(processes) as pool:
            return pool.map(_play_task, tasks)
    return [_play_task(t) for t in tasks]


# --------------------------------------------------------------------------- #
# Round-robin (relative fitness).
# --------------------------------------------------------------------------- #
def round_robin(
    individuals: list[tuple[str, Genome]],
    depth: int = 2,
    max_plies: int = 160,
    processes: int | None = None,
    keep_pgn: bool = False,
    log_moves: bool = False,
) -> tuple[dict[str, float], list[GameRecord]]:
    """Play a full double round-robin (each pair plays both colours).

    ``individuals`` is a list of ``(id, genome)``. Returns ``(scores, games)``
    where ``scores[id]`` is the genome's total tournament score. Set
    ``log_moves`` to record each game's FEN/eval trace (for the showcase).
    """
    tasks: list[tuple] = []
    for i in range(len(individuals)):
        ai, ag = individuals[i]
        ak = genome_kind(ag)
        for j in range(i + 1, len(individuals)):
            bi, bg = individuals[j]
            bk = genome_kind(bg)
            av, bv = ag.to_vector(), bg.to_vector()
            tasks.append((ai, av, ak, bi, bv, bk, depth, max_plies, None, keep_pgn, log_moves))
            tasks.append((bi, bv, bk, ai, av, ak, depth, max_plies, None, keep_pgn, log_moves))

    games = _run_tasks(tasks, processes)

    scores = {ind_id: 0.0 for ind_id, _ in individuals}
    for g in games:
        s = _SCORE[g.result]
        scores[g.white_id] += s
        scores[g.black_id] += 1.0 - s
    return scores, games


# --------------------------------------------------------------------------- #
# Benchmark vs a fixed baseline (absolute strength — the curve).
# --------------------------------------------------------------------------- #
def make_openings(count: int, plies: int = 2, seed: int = 12345) -> list[list[str]]:
    """A reproducible set of short random openings (lists of UCI moves).

    Using the *same* set every generation makes benchmark win-rates comparable
    across generations, and varying the start avoids one deterministic game.
    """
    rng = random.Random(seed)
    openings: list[list[str]] = []
    for _ in range(count):
        board = __import__("chess").Board()
        moves: list[str] = []
        for _ in range(plies):
            legal = list(board.legal_moves)
            move = rng.choice(legal)
            board.push(move)
            moves.append(move.uci())
        openings.append(moves)
    return openings


def benchmark(
    candidate: Genome,
    baseline: Genome,
    openings: list[list[str]],
    depth: int = 2,
    max_plies: int = 160,
    processes: int | None = None,
) -> float:
    """Win-rate (0..1) of ``candidate`` vs ``baseline``, both colours per opening."""
    cv, bv = candidate.to_vector(), baseline.to_vector()
    ck, bk = genome_kind(candidate), genome_kind(baseline)
    tasks: list[tuple] = []
    for opening in openings:
        # candidate as White, then candidate as Black, from the same opening.
        tasks.append(("cand", cv, ck, "base", bv, bk, depth, max_plies, opening, False, False))
        tasks.append(("base", bv, bk, "cand", cv, ck, depth, max_plies, opening, False, False))

    games = _run_tasks(tasks, processes)

    total = 0.0
    for g in games:
        s = _SCORE[g.result]
        total += s if g.white_id == "cand" else 1.0 - s
    return total / len(games) if games else 0.0
