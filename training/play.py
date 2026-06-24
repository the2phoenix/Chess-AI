"""Play against the Phase 1 engine from the terminal.

A minimal way to feel the engine out by hand before the web frontend exists.
Enter moves in SAN (e.g. ``Nf3``, ``e4``, ``O-O``) or UCI (e.g. ``g1f3``).
Type ``help`` for commands.

Usage:
    python play.py                  # you are White, engine depth 3
    python play.py --color black
    python play.py --depth 4
    python play.py --time 1.0       # engine gets 1s/move
"""

from __future__ import annotations

import argparse
import sys

import chess

from engine import Engine


def _parse_move(board: chess.Board, text: str) -> chess.Move | None:
    """Accept SAN or UCI; return a legal move or None."""
    text = text.strip()
    for parse in (board.parse_san, board.parse_uci):
        try:
            move = parse(text)
        except ValueError:
            continue
        if move in board.legal_moves:
            return move
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play Darwin's Gambit (Phase 1)")
    parser.add_argument("--color", choices=["white", "black"], default="white", help="the color YOU play")
    parser.add_argument("--depth", type=int, default=3, help="engine search depth")
    parser.add_argument("--time", type=float, default=None, help="engine seconds per move")
    args = parser.parse_args(argv)

    human_color = chess.WHITE if args.color == "white" else chess.BLACK
    engine = Engine(depth=args.depth, time_limit=args.time, name="Darwin")
    board = chess.Board()

    print("Darwin's Gambit — you vs the engine.")
    print("Enter moves in SAN (e4, Nf3, O-O) or UCI (e2e4). Commands: help, board, fen, quit.\n")
    print(board, "\n")

    while not board.is_game_over(claim_draw=True):
        if board.turn == human_color:
            move = _prompt_human(board)
            if move is None:  # user quit
                return 0
        else:
            print("Engine is thinking…")
            result = engine.analyse(board)
            move = result.move
            san = board.san(move)
            print(f"Engine plays {san}  (eval {engine.eval_bar_score(board):+d}cp after move, depth {result.depth})")

        board.push(move)
        print()
        print(board, "\n")

    print(f"Game over: {board.result(claim_draw=True)}")
    return 0


def _prompt_human(board: chess.Board) -> chess.Move | None:
    """Loop until the human enters a legal move or quits. None = quit."""
    while True:
        try:
            text = input("Your move: ")
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return None

        cmd = text.strip().lower()
        if cmd in ("quit", "exit", "q"):
            print("Bye.")
            return None
        if cmd in ("help", "h", "?"):
            print("Enter a move in SAN (e4, Nf3, O-O) or UCI (e2e4).")
            print("Commands: board (reprint), fen (show FEN), quit.")
            continue
        if cmd == "board":
            print(board)
            continue
        if cmd == "fen":
            print(board.fen())
            continue

        move = _parse_move(board, text)
        if move is None:
            print("Illegal or unparseable move. Try again (or 'help').")
            continue
        return move


if __name__ == "__main__":
    sys.exit(main())
