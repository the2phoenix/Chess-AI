"""Handcrafted evaluation function (Phase 1 MVP).

The score of a position is a weighted sum of human-understandable features:

    score = w_material      * material
          + w_piece_square  * piece_square_tables
          + w_mobility       * mobility
          + w_king_safety    * king_safety
          + w_pawn_structure * pawn_structure

The vector of weights is the **genome**. In Phase 1 we use one sensible,
hand-tuned :data:`DEFAULT_GENOME`. In Phase 2 the genetic algorithm will evolve
this vector through self-play — which is why the weights live in a small,
serialisable :class:`Genome` with ``to_vector`` / ``from_vector`` helpers.

Scores are returned from White's point of view, in centipawns
(100 = one pawn). Positive favours White, negative favours Black.

No human chess *strategy* is hard-coded beyond the feature definitions and the
default weights — and those weights are exactly what the GA is free to overturn.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, fields

import chess


# --------------------------------------------------------------------------- #
# Material
# --------------------------------------------------------------------------- #
# Base piece values in centipawns. The king is priceless for material purposes
# (checkmate is handled by the search, not the material count).
PIECE_VALUES: dict[chess.PieceType, int] = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}


# --------------------------------------------------------------------------- #
# Piece-square tables (middlegame), from White's perspective, square A1..H8.
# They encode "where pieces like to stand" — center control, knight outposts,
# rooks on open files-ish, king tucked away. Values are small nudges in
# centipawns. For Black we mirror the table vertically.
# --------------------------------------------------------------------------- #
# fmt: off
_PAWN_PST = [
      0,   0,   0,   0,   0,   0,   0,   0,
      5,  10,  10, -20, -20,  10,  10,   5,
      5,  -5, -10,   0,   0, -10,  -5,   5,
      0,   0,   0,  20,  20,   0,   0,   0,
      5,   5,  10,  25,  25,  10,   5,   5,
     10,  10,  20,  30,  30,  20,  10,  10,
     50,  50,  50,  50,  50,  50,  50,  50,
      0,   0,   0,   0,   0,   0,   0,   0,
]
_KNIGHT_PST = [
    -50, -40, -30, -30, -30, -30, -40, -50,
    -40, -20,   0,   5,   5,   0, -20, -40,
    -30,   5,  10,  15,  15,  10,   5, -30,
    -30,   0,  15,  20,  20,  15,   0, -30,
    -30,   5,  15,  20,  20,  15,   5, -30,
    -30,   0,  10,  15,  15,  10,   0, -30,
    -40, -20,   0,   0,   0,   0, -20, -40,
    -50, -40, -30, -30, -30, -30, -40, -50,
]
_BISHOP_PST = [
    -20, -10, -10, -10, -10, -10, -10, -20,
    -10,   5,   0,   0,   0,   0,   5, -10,
    -10,  10,  10,  10,  10,  10,  10, -10,
    -10,   0,  10,  10,  10,  10,   0, -10,
    -10,   5,   5,  10,  10,   5,   5, -10,
    -10,   0,   5,  10,  10,   5,   0, -10,
    -10,   0,   0,   0,   0,   0,   0, -10,
    -20, -10, -10, -10, -10, -10, -10, -20,
]
_ROOK_PST = [
      0,   0,   0,   5,   5,   0,   0,   0,
     -5,   0,   0,   0,   0,   0,   0,  -5,
     -5,   0,   0,   0,   0,   0,   0,  -5,
     -5,   0,   0,   0,   0,   0,   0,  -5,
     -5,   0,   0,   0,   0,   0,   0,  -5,
     -5,   0,   0,   0,   0,   0,   0,  -5,
      5,  10,  10,  10,  10,  10,  10,   5,
      0,   0,   0,   0,   0,   0,   0,   0,
]
_QUEEN_PST = [
    -20, -10, -10,  -5,  -5, -10, -10, -20,
    -10,   0,   5,   0,   0,   0,   0, -10,
    -10,   5,   5,   5,   5,   5,   0, -10,
      0,   0,   5,   5,   5,   5,   0,  -5,
     -5,   0,   5,   5,   5,   5,   0,  -5,
    -10,   0,   5,   5,   5,   5,   0, -10,
    -10,   0,   0,   0,   0,   0,   0, -10,
    -20, -10, -10,  -5,  -5, -10, -10, -20,
]
_KING_PST = [
     20,  30,  10,   0,   0,  10,  30,  20,
     20,  20,   0,   0,   0,   0,  20,  20,
    -10, -20, -20, -20, -20, -20, -20, -10,
    -20, -30, -30, -40, -40, -30, -30, -20,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
]
# fmt: on

_PIECE_SQUARE_TABLES: dict[chess.PieceType, list[int]] = {
    chess.PAWN: _PAWN_PST,
    chess.KNIGHT: _KNIGHT_PST,
    chess.BISHOP: _BISHOP_PST,
    chess.ROOK: _ROOK_PST,
    chess.QUEEN: _QUEEN_PST,
    chess.KING: _KING_PST,
}


# --------------------------------------------------------------------------- #
# The genome — the evolvable weight vector.
# --------------------------------------------------------------------------- #
@dataclass
class Genome:
    """Weights for the evaluation features.

    Each weight scales one feature's contribution to the final score. The
    :data:`DEFAULT_GENOME` below is hand-tuned to play sensible chess; Phase 2's
    GA will evolve these numbers via self-play. ``1.0`` means "use the feature
    at its natural scale".
    """

    material: float = 1.0
    piece_square: float = 1.0
    mobility: float = 1.0
    king_safety: float = 1.0
    pawn_structure: float = 1.0

    # -- serialisation helpers (used by the GA and by JSON weight files) ----- #
    def to_vector(self) -> list[float]:
        """Flatten to a plain list, in declared field order."""
        return [getattr(self, f.name) for f in fields(self)]

    @classmethod
    def from_vector(cls, vector) -> "Genome":
        """Rebuild from a flat list/array, in declared field order."""
        names = [f.name for f in fields(cls)]
        if len(vector) != len(names):
            raise ValueError(
                f"expected {len(names)} weights {names}, got {len(vector)}"
            )
        return cls(**{name: float(v) for name, v in zip(names, vector)})

    def to_dict(self) -> dict[str, float]:
        """JSON-friendly dict (language-agnostic; Python writes, JS reads)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Genome":
        names = {f.name for f in fields(cls)}
        return cls(**{k: float(v) for k, v in data.items() if k in names})


#: Sensible hand-tuned starting weights. Material dominates; the positional
#: features are gentle nudges (their raw scale is already small).
DEFAULT_GENOME = Genome(
    material=1.0,
    piece_square=1.0,
    mobility=1.0,
    king_safety=1.0,
    pawn_structure=1.0,
)


# --------------------------------------------------------------------------- #
# Individual features. Each returns a raw score from White's perspective
# (positive = good for White), before the genome weight is applied.
# --------------------------------------------------------------------------- #
def _material_and_piece_square(board: chess.Board) -> tuple[int, int]:
    """Walk the board once, accumulating material and piece-square scores."""
    material = 0
    piece_square = 0
    for square, piece in board.piece_map().items():
        value = PIECE_VALUES[piece.piece_type]
        pst = _PIECE_SQUARE_TABLES[piece.piece_type]
        if piece.color == chess.WHITE:
            material += value
            piece_square += pst[square]
        else:
            material -= value
            # Mirror the square vertically for Black.
            piece_square -= pst[chess.square_mirror(square)]
    return material, piece_square


def _mobility(board: chess.Board) -> int:
    """Difference in legal-move count (side to move vs the other side).

    More available moves ≈ more active pieces. Computed for both colours so the
    feature is symmetric and side-to-move-independent.
    """
    white_moves = _legal_move_count(board, chess.WHITE)
    black_moves = _legal_move_count(board, chess.BLACK)
    return white_moves - black_moves


def _legal_move_count(board: chess.Board, color: chess.Color) -> int:
    if board.turn == color:
        return board.legal_moves.count()
    # Count the other side's moves by flipping the side to move on a copy.
    mirror = board.copy(stack=False)
    mirror.turn = color
    # A null-move-style flip can expose an "in check" inconsistency; guard it.
    if mirror.is_valid():
        return mirror.legal_moves.count()
    return 0


# Squares directly around the king, used for a crude king-safety shield score.
def _king_safety(board: chess.Board) -> int:
    """Reward friendly pawns shielding each king; penalise an exposed king."""
    return _king_shield(board, chess.WHITE) - _king_shield(board, chess.BLACK)


def _king_shield(board: chess.Board, color: chess.Color) -> int:
    king_square = board.king(color)
    if king_square is None:
        return 0
    shield = 0
    file = chess.square_file(king_square)
    rank = chess.square_rank(king_square)
    # Look one rank in front of the king (toward the enemy) across 3 files.
    forward = 1 if color == chess.WHITE else -1
    shield_rank = rank + forward
    if 0 <= shield_rank <= 7:
        for df in (-1, 0, 1):
            f = file + df
            if 0 <= f <= 7:
                sq = chess.square(f, shield_rank)
                piece = board.piece_at(sq)
                if piece and piece.piece_type == chess.PAWN and piece.color == color:
                    shield += 10
    return shield


def _pawn_structure(board: chess.Board) -> int:
    """Penalise doubled and isolated pawns (symmetric for both colours)."""
    return _pawn_penalty(board, chess.WHITE) - _pawn_penalty(board, chess.BLACK)


def _pawn_penalty(board: chess.Board, color: chess.Color) -> int:
    pawns = board.pieces(chess.PAWN, color)
    files = [0] * 8
    for sq in pawns:
        files[chess.square_file(sq)] += 1

    penalty = 0
    for f in range(8):
        count = files[f]
        if count == 0:
            continue
        # Doubled (or tripled) pawns: penalise each extra pawn on the file.
        if count > 1:
            penalty -= 15 * (count - 1)
        # Isolated pawn: no friendly pawn on either adjacent file.
        left = files[f - 1] if f > 0 else 0
        right = files[f + 1] if f < 7 else 0
        if left == 0 and right == 0:
            penalty -= 15 * count
    return penalty


# --------------------------------------------------------------------------- #
# Public evaluation entry point.
# --------------------------------------------------------------------------- #
def evaluate(board: chess.Board, genome: Genome = DEFAULT_GENOME) -> int:
    """Static evaluation of ``board`` from White's perspective, in centipawns.

    Terminal positions are scored decisively here as a convenience, but note the
    search assigns mate scores itself; this keeps the static eval honest when
    called directly. Positive favours White.
    """
    if board.is_checkmate():
        # Side to move is mated → catastrophic for them.
        return -100_000 if board.turn == chess.WHITE else 100_000
    if board.is_stalemate() or board.is_insufficient_material():
        return 0

    material, piece_square = _material_and_piece_square(board)

    score = (
        genome.material * material
        + genome.piece_square * piece_square
        + genome.mobility * _mobility(board)
        + genome.king_safety * _king_safety(board)
        + genome.pawn_structure * _pawn_structure(board)
    )
    return int(score)
