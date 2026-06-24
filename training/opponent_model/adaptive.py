"""The adaptive opponent — a fixed strong engine that exploits *this* user.

Mode F3. The base engine (any genome — scalar or NN) is untouched: we never
fine-tune it on the user's games (GSD §4 warns that leads to catastrophic
forgetting). Instead, at move time, the :class:`AdaptiveEngine` asks the
per-user :class:`~opponent_model.model.OpponentModel`, "what will *this* player
probably do in reply?" and steers toward lines where their likely (often
habitual, often weak) reply hurts them most.

Two honesty guards keep it strong, not gimmicky:

* **Unknown ⇒ assume best.** Where the model has never seen the position, we
  assume the user finds the objectively best reply, so the adaptive engine
  falls back to the base engine's strong move. It only deviates where it
  genuinely *knows* a habit to punish.
* **Never self-harm.** It will only deviate from the base engine's best move if
  the new move is still close to it in raw strength (within a safety margin),
  so a wrong prediction can't make it hang material.

How hard it leans on the exploit scales with
:meth:`~opponent_model.model.OpponentModel.difficulty` — a player it has seen
more of meets a sharper opponent.
"""

from __future__ import annotations

import chess

from engine import Engine, Genome, DEFAULT_GENOME, NNGenome
from engine.evaluation import evaluate
from engine.nn_eval import nn_evaluate
from .model import OpponentModel

# Only consider this many of the base engine's candidate moves for the exploit
# pass (ranked by a cheap static eval) — bounds cost for interactive play.
_CANDIDATES = 8
# A deviation from the base-best move is allowed only if its own static score is
# within this many centipawns of the base-best (so we never blunder to bait).
_SAFETY_CP = 120


class AdaptiveEngine:
    """A strong base engine + a per-user exploit layer.

    Parameters
    ----------
    model:
        The user's :class:`OpponentModel` (mutated as games are observed).
    genome:
        The fixed base evaluation (scalar :class:`Genome` or :class:`NNGenome`).
    depth:
        Base search depth for the strong move.
    """

    def __init__(
        self,
        model: OpponentModel,
        genome: Genome | NNGenome | None = None,
        depth: int = 3,
    ) -> None:
        self.model = model
        self.genome = genome if genome is not None else DEFAULT_GENOME
        self.base = Engine(genome=self.genome, depth=depth, name="Adaptive")

    # --- play ----------------------------------------------------------- #
    def select_move(self, board: chess.Board) -> chess.Move | None:
        """Pick the AI's move: the base-best, or an exploit when one is known."""
        result = self.base.analyse(board)
        base_move = result.move
        if base_move is None:
            return None

        strength = self.model.difficulty()
        if strength <= 0.0:
            return base_move  # cold model: play the plain strong move

        ai_color = board.turn
        base_static = _static_after(board, base_move, ai_color, self.genome)

        # Value the base-best move and a few alternatives by how the *predicted*
        # user handles the reply — higher is better for the AI.
        scored = [(base_move, self._exploit_value(board, base_move, ai_color))]
        for move in self._candidates(board, ai_color, exclude=base_move):
            scored.append((move, self._exploit_value(board, move, ai_color)))

        base_value = scored[0][1]
        best_move, best_value = max(scored, key=lambda mv: mv[1])
        if best_move == base_move:
            return base_move

        # Guard 1: the exploit must beat the base move by a difficulty-scaled
        # edge (a timid model barely deviates; a warmed-up one leans in).
        edge = (1.0 - strength) * 120.0
        if best_value < base_value + edge:
            return base_move

        # Guard 2: never self-harm — the deviation must stay near base strength.
        if _static_after(board, best_move, ai_color, self.genome) < base_static - _SAFETY_CP:
            return base_move

        return best_move

    # --- internals ------------------------------------------------------ #
    def _candidates(self, board: chess.Board, ai_color: bool, exclude: chess.Move):
        """Top-K legal AI moves by static eval (cheap pre-filter)."""
        scored = []
        for move in board.legal_moves:
            if move == exclude:
                continue
            scored.append((_static_after(board, move, ai_color, self.genome), move))
        scored.sort(key=lambda sm: -sm[0])
        return [move for _, move in scored[:_CANDIDATES]]

    def _exploit_value(self, board: chess.Board, ai_move: chess.Move, ai_color: bool) -> float:
        """Expected AI advantage after ``ai_move``, given the predicted reply.

        Known position ⇒ average over the user's habitual replies (their real
        distribution). Unknown ⇒ assume the user finds their best reply, which
        recovers the base engine's pessimistic (correct) view.
        """
        board.push(ai_move)
        try:
            if board.is_game_over():
                return float(_static_for(board, ai_color, self.genome))
            preds = self.model.predict_reply(board)
            if preds:
                value = 0.0
                for uci, prob in preds.items():
                    try:
                        reply = chess.Move.from_uci(uci)
                    except ValueError:
                        continue
                    if reply not in board.legal_moves:
                        continue
                    value += prob * self._value_after_reply(board, reply, ai_color)
                if value != 0.0 or any(
                    chess.Move.from_uci(u) in board.legal_moves for u in preds
                ):
                    return value
            # Unknown / unusable prediction: assume the user replies optimally.
            return self._user_best_value(board, ai_color)
        finally:
            board.pop()

    def _value_after_reply(self, board: chess.Board, reply: chess.Move, ai_color: bool) -> float:
        board.push(reply)
        value = float(_static_for(board, ai_color, self.genome))
        board.pop()
        return value

    def _user_best_value(self, board: chess.Board, ai_color: bool) -> float:
        """AI value assuming the user picks the reply worst for the AI."""
        worst = None
        for reply in board.legal_moves:
            v = self._value_after_reply(board, reply, ai_color)
            if worst is None or v < worst:
                worst = v
        return worst if worst is not None else float(_static_for(board, ai_color, self.genome))

    # --- learning ------------------------------------------------------- #
    def learn_game(self, moves: list[chess.Move], user_color: bool) -> None:
        """After a game, fold the user's moves into the model (call once)."""
        self.model.observe_game(moves, user_color)


def _static_for(board: chess.Board, color: bool, genome) -> int:
    """Static eval from ``color``'s perspective, using the base genome."""
    if isinstance(genome, NNGenome):
        white = nn_evaluate(board, genome)
    else:
        white = evaluate(board, genome)
    return white if color == chess.WHITE else -white


def _static_after(board: chess.Board, move: chess.Move, color: bool, genome) -> int:
    board.push(move)
    score = _static_for(board, color, genome)
    board.pop()
    return score
