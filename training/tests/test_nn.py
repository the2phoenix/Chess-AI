"""Phase 6 (V2) tests: the neural-net evaluator is sane and can drive an engine.

Run from training/:
    python tests/test_nn.py
"""

from __future__ import annotations

import os
import random
import sys

import chess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import Engine, NNGenome, nn_evaluate, random_nn, NN_PARAMS, nn_features
from engine.nn_eval import N_IN


def test_features_have_expected_width():
    feats = nn_features(chess.Board())
    assert len(feats) == N_IN


def test_nn_genome_roundtrips():
    rng = random.Random(0)
    g = random_nn(rng)
    assert len(g.to_vector()) == NN_PARAMS
    assert NNGenome.from_vector(g.to_vector()).to_vector() == g.to_vector()
    assert NNGenome.from_dict(g.to_dict()).to_vector() == g.to_vector()


def test_nn_genome_wrong_length_raises():
    try:
        NNGenome.from_vector([0.0, 1.0])
    except ValueError:
        return
    raise AssertionError("expected ValueError for wrong-length NN vector")


def test_nn_evaluate_returns_int_and_handles_terminal():
    rng = random.Random(1)
    g = random_nn(rng)
    score = nn_evaluate(chess.Board(), g)
    assert isinstance(score, int)
    # Black is checkmated -> decisively good for White, regardless of weights.
    mated = chess.Board("k6Q/8/1K6/8/8/8/8/8 b - - 0 1")
    assert nn_evaluate(mated, g) > 50_000


def test_nn_engine_plays_a_legal_game():
    """An NN-genome engine drives the real search and produces only legal moves."""
    rng = random.Random(2)
    white = Engine(genome=random_nn(rng), depth=2, name="NN-W")
    black = Engine(genome=random_nn(rng), depth=2, name="NN-B")
    board = chess.Board()
    plies = 0
    while not board.is_game_over(claim_draw=True) and plies < 40:
        engine = white if board.turn == chess.WHITE else black
        move = engine.select_move(board)
        assert move is not None and move in board.legal_moves
        board.push(move)
        plies += 1
    assert board.is_valid()


def test_nn_evolution_runs():
    """The GA can evolve NN genomes end-to-end (genome-agnostic loop)."""
    from ga import evolve, EvolutionConfig

    cfg = EvolutionConfig(
        population=4, generations=2, depth=1, max_plies=30,
        benchmark_openings=2, processes=1, seed=0, genome_kind="nn",
    )
    result = evolve(cfg)
    assert isinstance(result.best.genome, NNGenome)
    assert len(result.best.genome.to_vector()) == NN_PARAMS
    assert len(result.run.generations) == 2
    for g in result.run.generations:
        # NN champion benchmarked vs the hand-tuned scalar baseline.
        assert 0.0 <= g.benchmark_winrate <= 1.0


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL  {name}: {exc}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"ERROR {name}: {exc!r}")
    print(f"\n{'ALL PASSED' if failures == 0 else f'{failures} FAILED'}")
    sys.exit(1 if failures else 0)
