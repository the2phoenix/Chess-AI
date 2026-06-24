"""The evolution loop (Phase 2 core).

Each generation:
  1. **Evaluate** — double round-robin gives every genome a fitness.
  2. **Benchmark** — the best genome plays the fixed baseline; its win-rate is
     the point on the strength curve.
  3. **Select + breed** — elites survive; the rest are children of tournament-
     selected parents via crossover + mutation, with every breeding recorded.

Defaults are intentionally small so a smoke run finishes quickly; pass a bigger
config (and ``processes``) for a real run. All heavy compute is offline.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, asdict
from typing import Callable

from engine import Genome, NNGenome, DEFAULT_GENOME, random_nn

from .genome_ops import random_genome, crossover, mutate, WEIGHT_MIN, WEIGHT_MAX
from .tournament import round_robin, benchmark, make_openings
from .lineage import BreedingRecord, GenerationRecord, RunRecord

# Mutation clamp bounds and initialisers per genome kind.
_NN_BOUND = 5.0


def _init_genome(kind: str, rng):
    return random_nn(rng, scale=0.5) if kind == "nn" else random_genome(rng)


def _from_vector(kind: str, vector):
    return NNGenome.from_vector(vector) if kind == "nn" else Genome.from_vector(vector)


def _mutate_bounds(kind: str) -> tuple[float, float]:
    return (-_NN_BOUND, _NN_BOUND) if kind == "nn" else (WEIGHT_MIN, WEIGHT_MAX)


@dataclass
class Individual:
    id: str
    genome: Genome
    fitness: float = 0.0


@dataclass
class EvolutionConfig:
    population: int = 16
    generations: int = 12
    depth: int = 2
    max_plies: int = 160
    elite: int = 2              # top individuals carried over unchanged
    tournament_k: int = 3       # parent-selection tournament size
    mutation_rate: float = 0.3
    mutation_sigma: float = 0.25
    benchmark_openings: int = 6
    processes: int | None = None
    seed: int = 0
    log_games: bool = False     # store every game's PGN (heavier on disk)
    log_moves: bool = False     # store each game's FEN/eval trace (for showcase)
    genome_kind: str = "scalar" # "scalar" (5 weights) | "nn" (evolve the network)
    # Phase 8 (continual pipeline) hooks:
    seed_genome: list | None = None    # warm-start: build gen-0 around this genome
    openings: list | None = None       # benchmark/start openings (e.g. from the pool)


@dataclass
class EvolutionResult:
    best: Individual
    run: RunRecord
    history: list[GenerationRecord] = field(default_factory=list)


def evolve(
    config: EvolutionConfig | None = None,
    on_generation: Callable[[GenerationRecord], None] | None = None,
) -> EvolutionResult:
    """Run the GA and return the best genome plus the full run record."""
    cfg = config or EvolutionConfig()
    rng = random.Random(cfg.seed)

    population = _initial_population(cfg, rng)
    openings = cfg.openings or make_openings(cfg.benchmark_openings, seed=cfg.seed + 999)

    run = RunRecord(config=asdict(cfg))
    best_overall: Individual | None = None
    best_winrate = -1.0

    for gen in range(cfg.generations):
        # 1. Evaluate this generation.
        scores, games = round_robin(
            [(ind.id, ind.genome) for ind in population],
            depth=cfg.depth,
            max_plies=cfg.max_plies,
            processes=cfg.processes,
            keep_pgn=cfg.log_games,
            log_moves=cfg.log_moves,
        )
        for ind in population:
            ind.fitness = scores[ind.id]
        population.sort(key=lambda x: x.fitness, reverse=True)
        best = population[0]

        # Snapshot the *evaluated* population now, before breeding replaces it.
        snapshot = [
            {"id": ind.id, "vector": ind.genome.to_vector(), "fitness": ind.fitness}
            for ind in population
        ]

        # 2. Absolute strength: best vs the fixed baseline.
        winrate = benchmark(
            best.genome,
            DEFAULT_GENOME,
            openings,
            depth=cfg.depth,
            max_plies=cfg.max_plies,
            processes=cfg.processes,
        )

        # Track the overall champion by *absolute* strength (win-rate vs the
        # baseline), tie-broken by relative fitness — that's the genome worth
        # shipping as weights.json, not merely the best in one noisy tournament.
        if (
            best_overall is None
            or winrate > best_winrate
            or (winrate == best_winrate and best.fitness > best_overall.fitness)
        ):
            best_overall = Individual(best.id, best.genome, best.fitness)
            best_winrate = winrate

        # 3. Breed the next generation (skip after the final evaluated one).
        breedings: list[BreedingRecord] = []
        if gen < cfg.generations - 1:
            population, breedings = _next_generation(population, gen + 1, cfg, rng)

        record = GenerationRecord(
            index=gen,
            best_id=best.id,
            best_vector=best.genome.to_vector(),
            best_fitness=best.fitness,
            benchmark_winrate=winrate,
            population=snapshot,
            breedings=breedings,
            games=games,
        )
        run.generations.append(record)
        if on_generation is not None:
            on_generation(record)

    assert best_overall is not None
    return EvolutionResult(best=best_overall, run=run, history=run.generations)


# --------------------------------------------------------------------------- #
# Initialisation
# --------------------------------------------------------------------------- #
def _initial_population(cfg: EvolutionConfig, rng: random.Random) -> list[Individual]:
    """Gen-0 population: random, or warm-started around ``seed_genome``.

    Warm-start (continual pipeline) keeps the current champion as-is and fills
    the rest of the population with mutated copies of it, so evolution *resumes*
    from the deployed strength instead of restarting from scratch.
    """
    if not cfg.seed_genome:
        return [
            Individual(id=f"g0-{i}", genome=_init_genome(cfg.genome_kind, rng))
            for i in range(cfg.population)
        ]
    seed = _from_vector(cfg.genome_kind, cfg.seed_genome)
    lo, hi = _mutate_bounds(cfg.genome_kind)
    pop = [Individual(id="g0-0", genome=seed)]  # the champion, unchanged
    for i in range(1, cfg.population):
        variant, _ = mutate(seed, rng, rate=cfg.mutation_rate, sigma=cfg.mutation_sigma, lo=lo, hi=hi)
        pop.append(Individual(id=f"g0-{i}", genome=variant))
    return pop


# --------------------------------------------------------------------------- #
# Selection + breeding
# --------------------------------------------------------------------------- #
def _next_generation(
    population: list[Individual],
    gen_index: int,
    cfg: EvolutionConfig,
    rng: random.Random,
) -> tuple[list[Individual], list[BreedingRecord]]:
    """Elites survive; the rest are bred from tournament-selected parents."""
    next_pop: list[Individual] = []
    breedings: list[BreedingRecord] = []

    # Elitism: carry the top individuals over unchanged (new ids, same genome).
    for i in range(min(cfg.elite, len(population))):
        elite = population[i]
        next_pop.append(Individual(id=f"g{gen_index}-{i}", genome=elite.genome))

    while len(next_pop) < cfg.population:
        parent_a = _tournament_select(population, cfg.tournament_k, rng)
        parent_b = _tournament_select(population, cfg.tournament_k, rng)
        child_id = f"g{gen_index}-{len(next_pop)}"

        lo, hi = _mutate_bounds(cfg.genome_kind)
        child_genome, mask = crossover(parent_a.genome, parent_b.genome, rng)
        child_genome, mutations = mutate(
            child_genome, rng, rate=cfg.mutation_rate, sigma=cfg.mutation_sigma, lo=lo, hi=hi
        )

        breedings.append(
            BreedingRecord(
                child_id=child_id,
                parent_a_id=parent_a.id,
                parent_a_vector=parent_a.genome.to_vector(),
                parent_b_id=parent_b.id,
                parent_b_vector=parent_b.genome.to_vector(),
                crossover_mask=mask,
                mutations=mutations,
                child_vector=child_genome.to_vector(),
            )
        )
        next_pop.append(Individual(id=child_id, genome=child_genome))

    return next_pop, breedings


def _tournament_select(
    population: list[Individual], k: int, rng: random.Random
) -> Individual:
    """Pick ``k`` random individuals and return the fittest."""
    contenders = rng.sample(population, min(k, len(population)))
    return max(contenders, key=lambda ind: ind.fitness)
