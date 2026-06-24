"""Darwin's Gambit chess engine (Phase 1 MVP).

Two parts, kept deliberately separate so the genetic algorithm (Phase 2) can
evolve evaluation without touching search:

- ``search``      : fixed minimax + alpha-beta (the part that never evolves).
- ``evaluation``  : the handcrafted, weighted evaluation (the *genome* — a
                    vector of weights the GA will later evolve).
- ``engine``      : ties them together into a simple ``Engine`` API.
"""

from .evaluation import Genome, DEFAULT_GENOME, evaluate
from .nn_eval import NNGenome, nn_evaluate, random_nn, N_PARAMS as NN_PARAMS, features as nn_features
from .search import search, SearchResult
from .engine import Engine
from .rules import (
    is_game_over,
    is_draw,
    is_threefold_repetition,
    is_perpetual_check,
    describe_termination,
    game_result,
)

__all__ = [
    "Genome",
    "DEFAULT_GENOME",
    "evaluate",
    "NNGenome",
    "nn_evaluate",
    "random_nn",
    "NN_PARAMS",
    "nn_features",
    "search",
    "SearchResult",
    "Engine",
    "is_game_over",
    "is_draw",
    "is_threefold_repetition",
    "is_perpetual_check",
    "describe_termination",
    "game_result",
]
