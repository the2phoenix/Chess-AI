"""Self-play demo — watch the Phase 1 engine play itself a full, legal game.

This is the Phase 1 acceptance check: it proves the engine produces only legal
moves and reaches a normal chess termination (checkmate, stalemate, draw, or the
move cap). Every move is validated against python-chess's legal move list before
it is played, so any illegal move would abort loudly.

Usage:
    python selfplay.py                     # default depth-3 game, prints PGN
    python selfplay.py --depth 2 --max-moves 120
    python selfplay.py --time 0.5          # 0.5s/move via iterative deepening
    python selfplay.py --pgn games/demo.pgn
    python selfplay.py --quiet             # only the result + PGN
"""

from __future__ import annotations

import argparse
import sys

import chess

from engine import Engine, describe_termination, is_game_over, game_result
from chess_io import game_to_pgn, save_pgn


def play_game(
    white: Engine,
    black: Engine,
    max_moves: int = 200,
    verbose: bool = True,
) -> chess.Board:
    """Play one engine-vs-engine game, validating every move is legal.

    ``max_moves`` counts full moves (a White+Black pair) before we stop and
    adjudicate a draw, so demos can't run unbounded.
    """
    board = chess.Board()

    while not is_game_over(board) and board.fullmove_number <= max_moves:
        engine = white if board.turn == chess.WHITE else black
        mover = "White" if board.turn == chess.WHITE else "Black"
        move_number = board.fullmove_number

        move = engine.select_move(board)
        if move is None:
            break

        # --- legality guard: the whole point of the Phase 1 check ----------- #
        if move not in board.legal_moves:
            raise RuntimeError(
                f"{engine.name} produced an ILLEGAL move {move} "
                f"in position {board.fen()}"
            )

        san = board.san(move)
        board.push(move)

        if verbose:
            eval_cp = engine.eval_bar_score(board)
            print(f"  {move_number:>3}. {mover:<5} {san:<7}  (eval {eval_cp:+d}cp)")

    return board


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Darwin's Gambit self-play demo")
    parser.add_argument("--depth", type=int, default=3, help="search depth (plies)")
    parser.add_argument("--time", type=float, default=None, help="seconds per move (overrides fixed depth via iterative deepening)")
    parser.add_argument("--max-moves", type=int, default=200, help="full-move cap before adjudicating a draw")
    parser.add_argument("--pgn", type=str, default=None, help="path to write the game PGN")
    parser.add_argument("--quiet", action="store_true", help="don't print every move")
    args = parser.parse_args(argv)

    white = Engine(depth=args.depth, time_limit=args.time, name="White")
    black = Engine(depth=args.depth, time_limit=args.time, name="Black")

    budget = f"{args.time}s/move" if args.time else f"depth {args.depth}"
    print(f"Darwin's Gambit — self-play demo ({budget})\n")

    board = play_game(white, black, max_moves=args.max_moves, verbose=not args.quiet)

    result = game_result(board)
    print(f"\nResult: {result}")
    print(f"Termination: {_describe_termination(board)}")
    print(f"Plies played: {len(board.move_stack)}")
    print(f"Final FEN: {board.fen()}")

    game = game_to_pgn(board, white_name=white.name, black_name=black.name)
    if args.pgn:
        path = save_pgn(game, args.pgn)
        print(f"\nPGN written to {path}")
    else:
        print("\nPGN:\n")
        print(game)

    return 0


def _describe_termination(board: chess.Board) -> str:
    # Shared rules (checkmate, stalemate, perpetual check, threefold, …).
    return describe_termination(board) or "move cap reached (adjudicated draw)"


if __name__ == "__main__":
    sys.exit(main())
