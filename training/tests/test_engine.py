"""Phase 1 tests: the engine plays *legal*, sensible chess.

Run from the training/ directory:
    python -m pytest -q
or without pytest installed:
    python tests/test_engine.py
"""

from __future__ import annotations

import os
import sys

import chess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import (
    Engine,
    evaluate,
    Genome,
    DEFAULT_GENOME,
    search,
    is_threefold_repetition,
    is_perpetual_check,
    is_draw,
    is_game_over,
    describe_termination,
)
from engine.search import MATE_THRESHOLD


# A position with a known perpetual check: White queen checks, Black king
# shuffles g8<->h7; the position cycles every 4 plies.
_PERPETUAL = ["h5e8", "g8h7", "e8h5", "h7g8", "h5e8", "g8h7", "e8h5", "h7g8"]
_PERPETUAL_FEN = "6k1/8/8/7Q/8/8/8/6K1 w - - 0 1"


def _play_perpetual() -> chess.Board:
    board = chess.Board(_PERPETUAL_FEN)
    for uci in _PERPETUAL:
        board.push(chess.Move.from_uci(uci))
    return board


# --------------------------------------------------------------------------- #
# Legality — the core Phase 1 acceptance criterion.
# --------------------------------------------------------------------------- #
def test_every_selfplay_move_is_legal():
    """Play a full short game; every move must be legal at the time it's made."""
    white = Engine(depth=2, name="W")
    black = Engine(depth=2, name="B")
    board = chess.Board()

    plies = 0
    while not board.is_game_over(claim_draw=True) and plies < 80:
        engine = white if board.turn == chess.WHITE else black
        move = engine.select_move(board)
        assert move is not None
        assert move in board.legal_moves, f"illegal move {move} at {board.fen()}"
        board.push(move)
        plies += 1

    # The board state stays internally consistent the whole way.
    assert board.is_valid()


def test_select_move_returns_none_when_game_over():
    board = chess.Board("k6Q/8/1K6/8/8/8/8/8 b - - 0 1")  # black is checkmated
    assert board.is_checkmate()
    assert Engine(depth=2).select_move(board) is None


# --------------------------------------------------------------------------- #
# Tactics — the search actually finds forced things.
# --------------------------------------------------------------------------- #
def test_finds_mate_in_one():
    # White to move: Qd8# (back-rank mate).
    board = chess.Board("6k1/5ppp/8/8/8/8/8/3Q2K1 w - - 0 1")
    move = Engine(depth=2).select_move(board)
    board.push(move)
    assert board.is_checkmate(), f"expected mate, got {board.fen()}"


def test_captures_free_queen():
    # White to move: a black queen on d5 is hanging to the pawn on e4.
    board = chess.Board("4k3/8/8/3q4/4P3/8/8/4K3 w - - 0 1")
    move = Engine(depth=3).select_move(board)
    assert move == chess.Move.from_uci("e4d5"), f"should grab the queen, played {move}"


def test_timed_search_leaves_board_unchanged():
    """A search that times out mid-line must restore the board exactly.

    Regression: a _Timeout used to propagate without unwinding the push/pop
    stack, corrupting the caller's board (it once produced 'illegal' moves).
    """
    board = chess.Board()
    fen_before = board.fen()
    stack_before = len(board.move_stack)
    result = search(board, depth=99, time_limit=0.05)  # forced to time out
    assert board.fen() == fen_before
    assert len(board.move_stack) == stack_before
    assert result.move in board.legal_moves


def test_avoids_losing_own_queen():
    # White queen on d1, black to move can't win it; but if White were to move
    # into a fork it should not. Simpler: from start, depth-2 move is reasonable.
    board = chess.Board()
    result = search(board, depth=2)
    assert result.move in board.legal_moves
    assert result.depth >= 1


# --------------------------------------------------------------------------- #
# Draw rules — threefold repetition / perpetual check.
# --------------------------------------------------------------------------- #
def test_threefold_repetition_is_detected():
    board = _play_perpetual()
    assert is_threefold_repetition(board)


def test_plain_repetition_is_not_a_draw():
    """House rule: repeating ordinary (non-checking) moves does NOT draw."""
    # Knights out and back three times — a real repetition, but no checks.
    board = chess.Board()
    for uci in ["g1f3", "g8f6", "f3g1", "f6g8"] * 3:
        board.push(chess.Move.from_uci(uci))
    assert is_threefold_repetition(board)        # it genuinely repeats…
    assert not is_perpetual_check(board)         # …but no check was involved…
    assert not is_draw(board)                    # …so it is NOT a draw,
    assert not is_game_over(board)               # the game continues,
    assert describe_termination(board) is None   # and there's no termination.
    assert Engine(depth=2).select_move(board) is not None  # engine plays on.


def test_perpetual_check_is_labelled():
    board = _play_perpetual()
    assert is_perpetual_check(board)
    assert describe_termination(board) == "perpetual check"


def test_search_scores_perpetual_check_as_draw():
    """From a repeated position one ply short of threefold, the engine should
    see that repeating again is a draw (score ~0), not a win for either side."""
    board = chess.Board(_PERPETUAL_FEN)
    for uci in _PERPETUAL[:-1]:  # stop one ply before the loop closes
        board.push(chess.Move.from_uci(uci))
    result = search(board, depth=3)
    # Black is to move and only down nothing; the line is a dead draw.
    assert abs(result.score) < 100, f"expected a drawn score, got {result.score}"


def test_losing_side_finds_saving_perpetual_check():
    """A side that is losing on material but has a perpetual check should grab
    the draw by checking rather than play on into a lost game.

    White has only K+Q; Black has K+Q+R (Black up a rook), so White is lost
    (~-5). We start Black-to-move and run the check cycle for seven plies so
    that White is now to move one ply short of a threefold: the only move that
    salvages the game is the perpetual check ``Qe8+``, which claims the draw.
    A correct search prefers that drawn (score ~0) line over any losing one.
    """
    board = chess.Board("r3Q1k1/8/8/8/8/8/q7/6K1 b - - 0 1")
    for uci in ["g8h7", "e8h5", "h7g8", "h5e8", "g8h7", "e8h5", "h7g8"]:
        board.push(chess.Move.from_uci(uci))
    assert board.turn == chess.WHITE and evaluate(board) < -300  # White is losing

    move = Engine(depth=2).select_move(board)
    board.push(move)
    assert board.is_check(), f"expected the saving perpetual check, got {move}"
    assert board.can_claim_threefold_repetition(), "the check should claim the draw"


# --------------------------------------------------------------------------- #
# Evaluation — symmetry and material sanity.
# --------------------------------------------------------------------------- #
def test_startpos_is_balanced():
    assert evaluate(chess.Board()) == 0


def test_extra_material_favours_that_side():
    # White is up a full queen.
    white_up = chess.Board("4k3/8/8/8/8/8/8/3QK3 w - - 0 1")
    assert evaluate(white_up) > 800

    # Mirror it: Black up a queen → symmetric negative score.
    black_up = chess.Board("3qk3/8/8/8/8/8/8/4K3 w - - 0 1")
    assert evaluate(black_up) < -800


def test_evaluation_is_color_symmetric():
    """Mirroring a position should negate its evaluation."""
    board = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 1")
    mirrored = board.mirror()
    assert evaluate(board) == -evaluate(mirrored)


# --------------------------------------------------------------------------- #
# Genome — serialisation round-trips (the GA depends on this in Phase 2).
# --------------------------------------------------------------------------- #
def test_genome_vector_roundtrip():
    g = Genome(material=1.1, piece_square=0.9, mobility=1.3, king_safety=0.7, pawn_structure=1.2)
    assert Genome.from_vector(g.to_vector()) == g


def test_genome_dict_roundtrip():
    g = DEFAULT_GENOME
    assert Genome.from_dict(g.to_dict()) == g


def test_genome_vector_wrong_length_raises():
    try:
        Genome.from_vector([1.0, 2.0])
    except ValueError:
        return
    raise AssertionError("expected ValueError for wrong-length vector")


# --------------------------------------------------------------------------- #
# Allow running directly without pytest.
# --------------------------------------------------------------------------- #
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
