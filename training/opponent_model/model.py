"""The per-user opponent model — what *this human* tends to do.

Phase 7 (Mode F3) keeps the strong base engine **fixed** and layers a small,
per-user profile on top (GSD §4: "opponent-modeling layer, base net
untouched"). This module is just the *profile*: it ingests a user's games and
remembers, per position, which moves they play and where they tend to go wrong.
:mod:`opponent_model.adaptive` then uses it to pick moves that exploit those
habits.

Deliberately statistical and cheap — no training, no net. It serialises to a
plain dict so the web layer can persist it per user (Supabase ``opponent_models``
row, or a local JSON file) and reload it next session.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import chess

from engine.evaluation import evaluate

# A user's move is flagged as a recurring mistake when it worsens their own
# static evaluation (their perspective) by at least this many centipawns.
BLUNDER_DROP_CP = 150

# Games seen before the per-user layer is considered "fully warmed up" (used to
# ramp difficulty — the AI sharpens against a user it has seen more of).
WARMUP_GAMES = 12


def position_key(board: chess.Board) -> str:
    """A clock-independent key for a position (placement, side, castling, ep).

    Two positions that are identical for play purposes share a key even if their
    move clocks differ, so habits transfer across games.
    """
    parts = board.fen().split(" ")
    return " ".join(parts[:4])


@dataclass
class OpponentModel:
    """A frequency profile of one user's play, keyed by position.

    Attributes
    ----------
    user_id:
        Opaque per-user id (Supabase user id, or any label).
    games_seen:
        How many of the user's games have been folded in (drives difficulty).
    move_stats:
        ``position_key -> {uci: count}`` — moves the user has played from each
        position they faced. The heart of the habit model.
    blunders:
        ``position_key -> {"move": uci, "drop": cp, "count": n}`` — positions
        where the user habitually played a move that worsened their own static
        eval by at least :data:`BLUNDER_DROP_CP`.
    opening_moves:
        ``uci -> count`` for the user's first move of each colour — a small,
        human-readable summary of opening tendencies (for the UI/profile).
    """

    user_id: str = "anon"
    games_seen: int = 0
    move_stats: dict[str, dict[str, int]] = field(default_factory=dict)
    blunders: dict[str, dict] = field(default_factory=dict)
    opening_moves: dict[str, int] = field(default_factory=dict)

    # --- ingest --------------------------------------------------------- #
    def observe_move(self, board: chess.Board, move: chess.Move) -> None:
        """Record that the user played ``move`` in ``board`` (their turn)."""
        key = position_key(board)
        bucket = self.move_stats.setdefault(key, {})
        uci = move.uci()
        bucket[uci] = bucket.get(uci, 0) + 1

        if board.fullmove_number == 1:
            self.opening_moves[uci] = self.opening_moves.get(uci, 0) + 1

        # Recurring-mistake detection: does the user's move worsen their own
        # standing once the opponent plays its best 1-ply reply? Including the
        # reply is what catches *tactical* blunders (hanging a piece to a
        # recapture), not just positional self-harm. Cheap: one ply, static.
        user_color = board.turn
        before = _eval_for(board, user_color)
        board.push(move)
        after = _opponent_best_reply_eval(board, user_color)
        board.pop()
        drop = before - after
        if drop >= BLUNDER_DROP_CP:
            rec = self.blunders.get(key)
            if rec is None or drop > rec["drop"]:
                self.blunders[key] = {"move": uci, "drop": int(drop), "count": 1}
            elif rec["move"] == uci:
                rec["count"] += 1

    def observe_game(self, moves: list[chess.Move], user_color: bool) -> None:
        """Fold a whole game in, recording only the *user's* moves.

        ``moves`` is the full move list from the standard start position;
        ``user_color`` is ``chess.WHITE``/``chess.BLACK`` — whichever side the
        human played. Engine moves are replayed but not learned from.
        """
        board = chess.Board()
        for move in moves:
            if board.turn == user_color:
                self.observe_move(board, move)
            board.push(move)
        self.games_seen += 1

    # --- query ---------------------------------------------------------- #
    def predict_reply(self, board: chess.Board) -> dict[str, float]:
        """The user's likely moves in ``board`` as a probability distribution.

        Returns ``{}`` when this position is unseen — the caller should then
        assume the user plays the objectively best reply (no exploit available).
        """
        bucket = self.move_stats.get(position_key(board))
        if not bucket:
            return {}
        total = sum(bucket.values())
        return {uci: n / total for uci, n in bucket.items()}

    def difficulty(self) -> float:
        """How sharp the per-user layer should play, in ``[0, 1]``.

        Ramps with games seen, so a returning player meets a tougher,
        better-informed opponent (PRD: "gets harder over repeated sessions").
        """
        return min(1.0, self.games_seen / WARMUP_GAMES)

    def summary(self) -> dict:
        """A small, human-readable digest for the profile/UI."""
        fav = sorted(self.opening_moves.items(), key=lambda kv: -kv[1])[:3]
        return {
            "user_id": self.user_id,
            "games_seen": self.games_seen,
            "positions_known": len(self.move_stats),
            "recurring_mistakes": len(self.blunders),
            "difficulty": round(self.difficulty(), 2),
            "favourite_openings": [uci for uci, _ in fav],
        }

    # --- persistence ---------------------------------------------------- #
    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "games_seen": self.games_seen,
            "move_stats": self.move_stats,
            "blunders": self.blunders,
            "opening_moves": self.opening_moves,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OpponentModel":
        return cls(
            user_id=data.get("user_id", "anon"),
            games_seen=int(data.get("games_seen", 0)),
            move_stats={k: dict(v) for k, v in data.get("move_stats", {}).items()},
            blunders={k: dict(v) for k, v in data.get("blunders", {}).items()},
            opening_moves=dict(data.get("opening_moves", {})),
        )


def _eval_for(board: chess.Board, color: bool) -> int:
    """Static evaluation from ``color``'s perspective (centipawns)."""
    white_score = evaluate(board)
    return white_score if color == chess.WHITE else -white_score


def _opponent_best_reply_eval(board: chess.Board, user_color: bool) -> int:
    """User-perspective eval after the opponent's best static 1-ply reply.

    The opponent (to move now) is assumed to pick the reply that minimises the
    user's evaluation — i.e. the recapture/refutation — so hanging material
    shows up as a large drop. Falls back to the static eval at terminal nodes.
    """
    if board.is_checkmate():
        # User just got mated (or delivered mate, but it's the opponent to
        # move, so this is the user being mated): worst possible for the user.
        return -100_000
    if not any(board.legal_moves):  # stalemate / no replies
        return _eval_for(board, user_color)
    worst = None
    for reply in board.legal_moves:
        board.push(reply)
        score = _eval_for(board, user_color)
        board.pop()
        if worst is None or score < worst:
            worst = score
    return worst
