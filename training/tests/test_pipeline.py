"""Phase 8 tests: the experience pool, the deploy registry, and the loop.

Kept tiny/fast (depth 1, a few games) — it checks the *plumbing* of the
continual loop, not that 2 generations produce a strong engine. Run from
training/:
    python tests/test_pipeline.py
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

import chess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import Engine, DEFAULT_GENOME, is_game_over
from experience_pool import ExperiencePool
import deploy
import pipeline


def _short_game(max_plies=20) -> chess.Board:
    w = Engine(depth=1, name="w")
    b = Engine(depth=1, name="b")
    board = chess.Board()
    while not is_game_over(board) and len(board.move_stack) < max_plies:
        mv = (w if board.turn == chess.WHITE else b).select_move(board)
        if mv is None:
            break
        board.push(mv)
    return board


def test_pool_add_and_stats():
    with tempfile.TemporaryDirectory() as d:
        pool = ExperiencePool(d)
        assert pool.size() == 0
        pool.add_board(_short_game(), source="self_play")
        pool.add_board(_short_game(), source="self_play")
        assert pool.size() == 2
        assert pool.count_by_source()["self_play"] == 2
        # Reload from disk -> index persists.
        reloaded = ExperiencePool(d)
        assert reloaded.size() == 2


def test_pool_sample_openings():
    with tempfile.TemporaryDirectory() as d:
        pool = ExperiencePool(d)
        for _ in range(5):
            pool.add_board(_short_game(max_plies=16), source="self_play")
        openings = pool.sample_openings(3, plies=6)
        assert len(openings) <= 3
        for line in openings:
            assert len(line) == 6
            # The opening must be a legal, replayable prefix.
            board = chess.Board()
            for uci in line:
                mv = chess.Move.from_uci(uci)
                assert mv in board.legal_moves
                board.push(mv)


def test_pool_empty_sample_is_empty():
    with tempfile.TemporaryDirectory() as d:
        pool = ExperiencePool(d)
        assert pool.sample_openings(4, plies=8) == []


def test_pool_add_pgn_roundtrips():
    with tempfile.TemporaryDirectory() as d:
        pool = ExperiencePool(d)
        board = _short_game()
        from chess_io import game_to_pgn
        pgn = str(game_to_pgn(board, white_name="You", black_name="AI"))
        entry = pool.add_pgn(pgn, source="human")
        assert entry.source == "human"
        assert pool.count_by_source()["human"] == 1


def test_deploy_registry_promote_and_load():
    with tempfile.TemporaryDirectory() as d:
        assert deploy.current_champion(d) is None
        g, kind = deploy.current_genome(d)
        assert kind == "scalar" and g.to_vector() == DEFAULT_GENOME.to_vector()

        v1 = deploy.promote(d, "scalar", DEFAULT_GENOME.to_vector(),
                            benchmark_winrate=0.6, vs_incumbent=0.55,
                            source_games=10, notes="t")
        assert v1["version"] == 1
        champ = deploy.current_champion(d)
        assert champ is not None and champ["version"] == 1
        # A second promotion bumps current to 2.
        v2 = deploy.promote(d, "scalar", DEFAULT_GENOME.to_vector(),
                            benchmark_winrate=0.65, vs_incumbent=0.56,
                            source_games=20)
        assert deploy.load_registry(d)["current"] == 2 and v2["version"] == 2


def test_pipeline_collect_then_train_cycle(monkeypatch=None):
    """End-to-end: collect a few games, then train one tiny gated generation."""
    with tempfile.TemporaryDirectory() as pool_dir, tempfile.TemporaryDirectory() as dep_dir:
        collect_args = argparse.Namespace(
            pool=pool_dir, deploy=dep_dir, kind="scalar", depth=1, max_plies=30,
            processes=1, seed=1, games=4,
        )
        assert pipeline.cmd_collect(collect_args) == 0
        assert ExperiencePool(pool_dir).size() == 4

        train_args = argparse.Namespace(
            pool=pool_dir, deploy=dep_dir, kind="scalar", depth=1, max_plies=30,
            processes=1, seed=1, population=6, generations=2,
            benchmark_openings=4, opening_plies=6, gate=-1.0,  # gate<0 => always promote
            deploy_web=False,
        )
        assert pipeline.cmd_train(train_args) == 0
        # With an always-pass gate, a champion must now be deployed.
        assert deploy.current_champion(dep_dir) is not None


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
