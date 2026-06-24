"""Genetic operators over the evaluation :class:`~engine.Genome` (Phase 2).

The genome is a short vector of real-valued weights (material, piece-square,
mobility, king-safety, pawn-structure). These are the operators the GA uses to
turn one generation into the next:

- :func:`random_genome` — a fresh individual for the initial population.
- :func:`crossover`     — uniform per-gene crossover of two parents.
- :func:`mutate`        — Gaussian perturbation of some genes.

Crossover and mutation also *report what they did* (which gene came from which
parent, what mutated and by how much). That record is what the Phase 3 "genomes
bonding" animation will replay — so the visual shows the real breeding, not a
fake. See :mod:`ga.lineage` for the record types.
"""

from __future__ import annotations

import random
from dataclasses import fields

from engine import Genome

from .lineage import MutationEvent

# Gene order is the genome's declared field order — the single source of truth.
GENE_NAMES: list[str] = [f.name for f in fields(Genome)]

# Weights are multipliers on evaluation features. We keep them non-negative (a
# negative material weight would mean "try to lose material") and bounded so a
# runaway mutation can't produce a nonsensical engine.
WEIGHT_MIN = 0.0
WEIGHT_MAX = 3.0

# Initial population spread: uniform around 1.0 (the hand-tuned default scale).
INIT_LO = 0.0
INIT_HI = 2.0


def random_genome(rng: random.Random, lo: float = INIT_LO, hi: float = INIT_HI) -> Genome:
    """A fresh genome with each gene drawn uniformly from ``[lo, hi]``."""
    return Genome.from_vector([rng.uniform(lo, hi) for _ in GENE_NAMES])


def crossover(a, b, rng: random.Random):
    """Uniform crossover: each gene is taken from parent ``a`` or ``b`` by coin flip.

    Genome-type-agnostic: the child is rebuilt as the *same type* as ``a`` (the
    scalar :class:`Genome` or the V2 :class:`NNGenome`), so the same GA evolves
    either. Returns the child genome and the ``mask`` (0 = from ``a``, 1 = from
    ``b``) so the breeding can be visualised.
    """
    va, vb = a.to_vector(), b.to_vector()
    mask = [rng.randint(0, 1) for _ in va]
    child = [vb[i] if mask[i] else va[i] for i in range(len(va))]
    return type(a).from_vector(child), mask


def _gene_label(i: int) -> str:
    return GENE_NAMES[i] if i < len(GENE_NAMES) else f"w{i}"


def mutate(
    genome,
    rng: random.Random,
    rate: float = 0.3,
    sigma: float = 0.25,
    lo: float = WEIGHT_MIN,
    hi: float = WEIGHT_MAX,
):
    """Perturb each gene with probability ``rate`` by Gaussian noise (``sigma``).

    Values are clamped to ``[lo, hi]`` (scalar weights use [0, 3]; NN weights a
    wider symmetric range). Genome-type-agnostic. Returns the mutated genome and
    the list of mutations that fired (for the lineage record).
    """
    v = genome.to_vector()
    events: list[MutationEvent] = []
    for i in range(len(v)):
        if rng.random() < rate:
            before = v[i]
            after = min(hi, max(lo, before + rng.gauss(0.0, sigma)))
            v[i] = after
            events.append(MutationEvent(gene=_gene_label(i), before=before, after=after))
    return type(genome).from_vector(v), events
