"""Phase 7 acceptance demo — the opponent model learns a user and sharpens.

We simulate a *habitual* human: a player who, faced with the same position,
tends to repeat the same (often second-best) move. The adaptive engine starts
cold (plays the plain strong base move), watches a few of the user's games, and
we show its per-user profile filling in — opening tendencies and recurring
mistakes — so it can start anticipating this specific player.

This is the honest Phase 7 check: not "instantly superhuman", but
"demonstrably builds and uses a per-user model" (GSD §4). Run from training/:

    python adaptive_demo.py
    python adaptive_demo.py --sessions 6 --depth 2
"""

from __future__ import annotations

import argparse
import random
import sys

import chess

from engine import Engine, is_game_over
from opponent_model import OpponentModel, AdaptiveEngine


class HabitualUser:
    """A deterministic-ish human: prefers a fixed favourite when it can, else
    plays a slightly random legal move (so games vary but habits recur)."""

    FAVOURITES = ["d7d5", "g8f6", "c7c6", "c8f5", "e7e6", "f8d6"]  # a Slav-ish habit

    def __init__(self, seed: int = 0) -> None:
        self.rng = random.Random(seed)

    def select_move(self, board: chess.Board) -> chess.Move:
        for uci in self.FAVOURITES:
            try:
                mv = chess.Move.from_uci(uci)
            except ValueError:
                continue
            if mv in board.legal_moves:
                return mv
        legal = list(board.legal_moves)
        return self.rng.choice(legal)


def play_session(ai: AdaptiveEngine, user: HabitualUser, max_plies: int = 80):
    """AI is White, the habitual user is Black. Returns (result, user_moves)."""
    board = chess.Board()
    user_moves: list[chess.Move] = []
    while not is_game_over(board) and len(board.move_stack) < max_plies:
        if board.turn == chess.WHITE:
            move = ai.select_move(board)
        else:
            move = user.select_move(board)
            user_moves.append(move)
        if move is None:
            break
        board.push(move)
    return board, user_moves


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 7 adaptive-opponent demo")
    parser.add_argument("--sessions", type=int, default=5, help="games to watch the user play")
    parser.add_argument("--depth", type=int, default=2, help="search depth")
    args = parser.parse_args(argv)

    model = OpponentModel(user_id="demo-user")
    ai = AdaptiveEngine(model, depth=args.depth)
    user = HabitualUser(seed=7)

    print("Phase 7 - adaptive opponent demo")
    print(f"AI (White, depth {args.depth}) vs a habitual user (Black), "
          f"{args.sessions} sessions.\n")
    print("session | result | difficulty | positions known | recurring mistakes")
    print("--------+--------+------------+-----------------+-------------------")

    for s in range(1, args.sessions + 1):
        board, user_moves = play_session(ai, user)
        # The model learns the user's full game (their colour = Black).
        all_moves = list(board.move_stack)
        ai.learn_game(all_moves, chess.BLACK)
        diff = model.difficulty()
        summ = model.summary()
        print(f"   {s:>4} | {board.result(claim_draw=True):<6} | "
              f"{diff:>10.2f} | {summ['positions_known']:>15} | "
              f"{summ['recurring_mistakes']:>18}")

    print("\nFinal per-user profile:")
    summ = model.summary()
    for k, v in summ.items():
        print(f"  {k}: {v}")

    # Show the model is *usable*: name the user's most-confident habit. Pick
    # the position the model has the most observations of and predict the reply.
    best_key = max(model.move_stats, key=lambda k: sum(model.move_stats[k].values()))
    bucket = model.move_stats[best_key]
    likely = max(bucket, key=bucket.get)
    conf = bucket[likely] / sum(bucket.values())
    print(f"\nMost-confident read on this user: in a position seen "
          f"{sum(bucket.values())}x, they reply {likely} (p={conf:.2f}).")

    print("\nThe base engine was never modified - all learning lives in the "
          "per-user model, exactly as Mode F3 intends.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
