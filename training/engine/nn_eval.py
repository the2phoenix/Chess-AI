"""Neural-network evaluator (Phase 6 / V2 kickoff).

A small multilayer perceptron that maps a handful of board features to a single
evaluation score (centipawns, White's perspective) — the V2 replacement for the
hand-weighted :func:`engine.evaluation.evaluate`. The network is *tiny* on
purpose (PROJECT_GUIDE.md: keep the NN small, search shallow), and there is no
backprop: the GA evolves the weights directly, exactly like the scalar genome.

Architecture: 10 inputs → 8 hidden (tanh) → 1 linear output, scaled to
centipawns. The flat weight vector (97 numbers) is the genome the GA evolves.

This module only does the *forward pass*; wiring it into the GA's evolve loop is
the next increment. It can already drive a real engine via the search's
pluggable-evaluator hook.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import chess

from .evaluation import (
    evaluate,
    DEFAULT_GENOME,
    _material_and_piece_square,
    _mobility,
    _king_safety,
    _pawn_structure,
)

N_IN = 10
N_HID = 8
N_OUT = 1
# Weight layout in the flat genome: W1, b1, W2, b2.
_W1 = N_HID * N_IN
_B1 = N_HID
_W2 = N_OUT * N_HID
_B2 = N_OUT
N_PARAMS = _W1 + _B1 + _W2 + _B2  # 97

# The network learns a *correction* (in centipawns) added to the handcrafted
# evaluation — a residual. So a near-zero net ≈ the handcrafted eval (starts at
# baseline strength), and evolution only has to find improvements on top.
CORRECTION_SCALE = 300.0


def features(board: chess.Board) -> np.ndarray:
    """A compact, *raw* (un-weighted) feature vector from White's perspective.

    These are the same human features the scalar eval uses, but handed to the
    network un-combined so it can learn its own weighting (and non-linear
    interactions the scalar sum can't express).
    """
    diff = {chess.PAWN: 0, chess.KNIGHT: 0, chess.BISHOP: 0, chess.ROOK: 0, chess.QUEEN: 0}
    for piece in board.piece_map().values():
        if piece.piece_type in diff:
            diff[piece.piece_type] += 1 if piece.color == chess.WHITE else -1
    _, piece_square = _material_and_piece_square(board)
    return np.array([
        diff[chess.PAWN] / 8.0,
        diff[chess.KNIGHT] / 2.0,
        diff[chess.BISHOP] / 2.0,
        diff[chess.ROOK] / 2.0,
        diff[chess.QUEEN] / 1.0,
        piece_square / 100.0,
        _mobility(board) / 20.0,
        _king_safety(board) / 30.0,
        _pawn_structure(board) / 30.0,
        1.0 if board.turn == chess.WHITE else -1.0,
    ], dtype=np.float64)


@dataclass
class NNGenome:
    """A flat weight vector for the evaluator MLP (the thing the GA evolves)."""

    weights: list[float]

    def to_vector(self) -> list[float]:
        return list(self.weights)

    @classmethod
    def from_vector(cls, vector) -> "NNGenome":
        v = list(vector)
        if len(v) != N_PARAMS:
            raise ValueError(f"expected {N_PARAMS} NN weights, got {len(v)}")
        return cls([float(x) for x in v])

    def to_dict(self) -> dict:
        return {"arch": [N_IN, N_HID, N_OUT], "weights": list(self.weights)}

    @classmethod
    def from_dict(cls, data: dict) -> "NNGenome":
        return cls.from_vector(data["weights"])

    def _unpack(self):
        # Cache the reshaped matrices: an engine reuses one genome across the
        # whole search, so we only pay the reshape once (big speedup at leaves).
        cache = getattr(self, "_arrays", None)
        if cache is None:
            w = np.asarray(self.weights, dtype=np.float64)
            i = 0
            W1 = w[i:i + _W1].reshape(N_HID, N_IN); i += _W1
            b1 = w[i:i + _B1]; i += _B1
            W2 = w[i:i + _W2].reshape(N_OUT, N_HID); i += _W2
            b2 = w[i:i + _B2]
            cache = (W1, b1, W2, b2)
            self._arrays = cache
        return cache


def random_nn(rng, scale: float = 0.3) -> NNGenome:
    """A fresh NN genome with small Gaussian weights (uses a stdlib ``Random``).

    Small weights → a small correction → the net starts near the handcrafted
    evaluation, so the initial population already plays at roughly baseline
    strength and evolution refines from there.
    """
    return NNGenome([rng.gauss(0.0, scale) for _ in range(N_PARAMS)])


def nn_evaluate(board: chess.Board, genome: NNGenome) -> int:
    """Static NN evaluation (White's perspective, centipawns).

    Residual design: handcrafted evaluation + a learned NN correction.
    """
    if board.is_checkmate():
        return -100_000 if board.turn == chess.WHITE else 100_000
    if board.is_stalemate() or board.is_insufficient_material():
        return 0

    base = evaluate(board, DEFAULT_GENOME)  # strong handcrafted starting point
    W1, b1, W2, b2 = genome._unpack()
    x = features(board)
    h = np.tanh(W1 @ x + b1)
    correction = float((W2 @ h + b2)[0]) * CORRECTION_SCALE
    return int(base + correction)
