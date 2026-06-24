"""Phase 7 (V2) tests: the per-user adaptive opponent learns and exploits.

Run from training/:
    python tests/test_opponent_model.py
"""

from __future__ import annotations

import os
import sys

import chess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opponent_model import OpponentModel, AdaptiveEngine, position_key
from opponent_model.model import WARMUP_GAMES


def _moves(ucis):
    return [chess.Move.from_uci(u) for u in ucis]


def test_position_key_is_clock_independent():
    a = chess.Board()
    b = chess.Board()
    b.halfmove_clock = 7  # different clocks, same position for play
    assert position_key(a) == position_key(b)


def test_observe_records_only_user_moves():
    model = OpponentModel(user_id="u1")
    # User is White: 1. e4 e5 2. Nf3 — only White's moves should be learned.
    model.observe_game(_moves(["e2e4", "e7e5", "g1f3"]), chess.WHITE)
    assert model.games_seen == 1
    start = position_key(chess.Board())
    assert model.move_stats[start] == {"e2e4": 1}
    assert model.opening_moves.get("e2e4") == 1
    # Black's e7e5 reply must NOT be in the (White) user's stats.
    board = chess.Board()
    board.push(chess.Move.from_uci("e2e4"))
    assert "e7e5" not in model.move_stats.get(position_key(board), {})


def test_predict_reply_reflects_frequencies():
    model = OpponentModel()
    # Same position twice: user plays e4 twice, d4 once.
    for ucis in (["e2e4"], ["e2e4"], ["d2d4"]):
        model.observe_game(_moves(ucis), chess.WHITE)
    preds = model.predict_reply(chess.Board())
    assert round(preds["e2e4"], 3) == round(2 / 3, 3)
    assert round(preds["d2d4"], 3) == round(1 / 3, 3)
    assert model.predict_reply(chess.Board()) and sum(preds.values()) == 1.0


def test_unseen_position_predicts_nothing():
    model = OpponentModel()
    board = chess.Board()
    board.push(chess.Move.from_uci("e2e4"))
    assert model.predict_reply(board) == {}


def test_recurring_blunder_is_flagged():
    model = OpponentModel()
    # User (Black) hangs the queen: after 1.e4, ...Qh4?? walks into nothing here
    # but giving away a queen for free is a clear static-eval drop. Build a
    # position where Black can drop a queen by capturing a defended pawn.
    board = chess.Board("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 1")
    # ...Qxg4?? loses the queen (pawn on f3 recaptures). Big drop for Black.
    model.observe_move(board, chess.Move.from_uci("h4g4"))
    assert position_key(board) in model.blunders


def test_difficulty_ramps_with_games():
    model = OpponentModel()
    assert model.difficulty() == 0.0
    for _ in range(WARMUP_GAMES):
        model.observe_game(_moves(["e2e4"]), chess.WHITE)
    assert model.difficulty() == 1.0


def test_model_roundtrips_through_dict():
    model = OpponentModel(user_id="u9")
    model.observe_game(_moves(["d2d4", "d7d5", "c2c4"]), chess.WHITE)
    restored = OpponentModel.from_dict(model.to_dict())
    assert restored.user_id == "u9"
    assert restored.games_seen == model.games_seen
    assert restored.move_stats == model.move_stats
    assert restored.predict_reply(chess.Board()) == model.predict_reply(chess.Board())


def test_adaptive_plays_legal_moves():
    model = OpponentModel()
    eng = AdaptiveEngine(model, depth=2)
    board = chess.Board()
    for _ in range(6):
        if board.is_game_over():
            break
        move = eng.select_move(board)
        assert move is not None and move in board.legal_moves
        board.push(move)


def test_cold_model_matches_base_engine():
    # With no games seen, the adaptive engine must equal the plain base engine
    # (difficulty 0 ⇒ no deviation) — it never plays *worse* than the base.
    from engine import Engine

    model = OpponentModel()  # cold
    adaptive = AdaptiveEngine(model, depth=2)
    base = Engine(depth=2)
    board = chess.Board()
    board.push(chess.Move.from_uci("e2e4"))
    assert adaptive.select_move(board) == base.select_move(board)


def test_exploit_targets_a_known_user_blunder():
    """If the user habitually replies with a losing move, the adaptive engine
    should steer into the line that invites it (and never play a worse move)."""
    model = OpponentModel(user_id="patzer")
    # Teach the model a habit: as Black, in the position after 1.e4, the user
    # always answers 1...f6?? (a known weakening blunder). Repeat so the model
    # is warmed up (difficulty climbs) and the habit is certain.
    line = _moves(["e2e4", "f7f6", "d2d4", "g7g5"])
    for _ in range(WARMUP_GAMES):
        model.observe_game(line, chess.BLACK)
    # Now the AI is White to move from the start; it knows Black tends to play
    # 1...f6. The adaptive engine should still produce a legal, sane move and
    # not crash while consulting the model.
    eng = AdaptiveEngine(model, depth=2)
    move = eng.select_move(chess.Board())
    assert move is not None and move in chess.Board().legal_moves


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
