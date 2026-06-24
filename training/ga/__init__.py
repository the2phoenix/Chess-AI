"""Darwin's Gambit genetic algorithm (Phase 2).

Evolves the evaluation :class:`~engine.Genome` (a short vector of feature
weights) through self-play tournaments. Search is fixed and shallow; only the
genome evolves.

Public surface:
- :func:`evolve` / :class:`EvolutionConfig` — run the GA.
- :func:`round_robin`, :func:`benchmark`     — score a population / measure
  absolute strength against the baseline.
- genetic operators (:func:`random_genome`, :func:`crossover`, :func:`mutate`).
- lineage record types — the JSON contract the Phase 3 showcase reads.
"""

from .genome_ops import random_genome, crossover, mutate, GENE_NAMES
from .match import play_match, GameOutcome
from .tournament import round_robin, benchmark, make_openings
from .evolution import evolve, EvolutionConfig, EvolutionResult, Individual
from .knockout import run_knockout, biased_crossover
from .lineage import (
    MutationEvent,
    BreedingRecord,
    GameRecord,
    GenerationRecord,
    RunRecord,
    write_run,
)

__all__ = [
    "random_genome",
    "crossover",
    "mutate",
    "GENE_NAMES",
    "play_match",
    "GameOutcome",
    "round_robin",
    "benchmark",
    "make_openings",
    "evolve",
    "EvolutionConfig",
    "EvolutionResult",
    "Individual",
    "run_knockout",
    "biased_crossover",
    "MutationEvent",
    "BreedingRecord",
    "GameRecord",
    "GenerationRecord",
    "RunRecord",
    "write_run",
]
