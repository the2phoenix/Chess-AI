"""Phase 2 tests: the genetic algorithm evolves evaluation weights.

These use tiny populations / shallow depth so they run fast and single-process.

Run from the training/ directory:
    python -m pytest -q tests/test_ga.py
or without pytest:
    python tests/test_ga.py
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import Genome, DEFAULT_GENOME
from ga import (
    random_genome,
    crossover,
    mutate,
    round_robin,
    benchmark,
    make_openings,
    evolve,
    EvolutionConfig,
    GENE_NAMES,
)
from ga.genome_ops import WEIGHT_MIN, WEIGHT_MAX


# --------------------------------------------------------------------------- #
# Genetic operators
# --------------------------------------------------------------------------- #
def test_random_genome_has_all_genes_in_range():
    rng = random.Random(1)
    g = random_genome(rng)
    vec = g.to_vector()
    assert len(vec) == len(GENE_NAMES)
    assert all(WEIGHT_MIN <= v <= WEIGHT_MAX for v in vec)


def test_crossover_takes_each_gene_from_a_parent():
    rng = random.Random(2)
    a = Genome.from_vector([0.1, 0.2, 0.3, 0.4, 0.5])
    b = Genome.from_vector([1.1, 1.2, 1.3, 1.4, 1.5])
    child, mask = crossover(a, b, rng)
    cv, av, bv = child.to_vector(), a.to_vector(), b.to_vector()
    assert len(mask) == len(cv)
    for i, gene in enumerate(cv):
        assert gene == (bv[i] if mask[i] else av[i])


def test_mutation_records_events_and_stays_in_bounds():
    rng = random.Random(3)
    g = Genome.from_vector([1.0] * len(GENE_NAMES))
    mutated, events = mutate(g, rng, rate=1.0, sigma=0.5)
    assert events, "rate=1.0 should mutate at least one gene"
    assert all(WEIGHT_MIN <= v <= WEIGHT_MAX for v in mutated.to_vector())
    for ev in events:
        assert ev.gene in GENE_NAMES


def test_zero_rate_mutation_is_a_noop():
    rng = random.Random(4)
    g = random_genome(rng)
    mutated, events = mutate(g, rng, rate=0.0)
    assert events == []
    assert mutated.to_vector() == g.to_vector()


# --------------------------------------------------------------------------- #
# Tournament
# --------------------------------------------------------------------------- #
def test_round_robin_conserves_points():
    rng = random.Random(5)
    individuals = [(f"i{i}", random_genome(rng)) for i in range(4)]
    scores, games = round_robin(individuals, depth=1, max_plies=40)
    # Double round-robin: N*(N-1) games, each distributing exactly 1.0 point.
    n = len(individuals)
    assert len(games) == n * (n - 1)
    assert abs(sum(scores.values()) - n * (n - 1)) < 1e-6
    assert set(scores) == {ind_id for ind_id, _ in individuals}


def test_benchmark_returns_a_fraction():
    openings = make_openings(2, plies=2, seed=7)
    wr = benchmark(DEFAULT_GENOME, DEFAULT_GENOME, openings, depth=1, max_plies=40)
    # Baseline vs itself: a valid win-rate in [0, 1] (≈ a draw, but determinism
    # plus material adjudication can tip it either way — just assert the range).
    assert 0.0 <= wr <= 1.0


# --------------------------------------------------------------------------- #
# Full evolution loop
# --------------------------------------------------------------------------- #
def test_evolution_runs_and_records_lineage():
    cfg = EvolutionConfig(
        population=4,
        generations=3,
        depth=1,
        max_plies=40,
        benchmark_openings=2,
        processes=1,
        seed=0,
    )
    result = evolve(cfg)

    # A best genome of the right shape.
    assert len(result.best.genome.to_vector()) == len(GENE_NAMES)
    # One record per generation.
    assert len(result.run.generations) == cfg.generations

    # Every non-final generation bred children, and each breeding is a real,
    # well-formed crossover record (what the bonding animation will replay).
    for gen in result.run.generations[:-1]:
        assert gen.breedings, "expected breeding records before the final gen"
        for rec in gen.breedings:
            assert len(rec.crossover_mask) == len(GENE_NAMES)
            assert len(rec.child_vector) == len(GENE_NAMES)
            assert rec.parent_a_id and rec.parent_b_id

    # Win-rates are valid fractions across the whole curve.
    for gen in result.run.generations:
        assert 0.0 <= gen.benchmark_winrate <= 1.0


# --------------------------------------------------------------------------- #
# Allow running directly without pytest.
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL  {name}: {exc}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"ERROR {name}: {exc!r}")
    print(f"\n{'ALL PASSED' if failures == 0 else f'{failures} FAILED'}")
    sys.exit(1 if failures else 0)
