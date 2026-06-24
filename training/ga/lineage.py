"""Records of *what the GA did* — so the showcase can replay real evolution.

These plain dataclasses are the on-disk contract between the offline GA and the
(future) Phase 3 frontend:

- :class:`BreedingRecord` — one crossover: the two parents, which gene came from
  which, and what mutated. Drives the "genomes bonding" animation.
- :class:`GameRecord`     — one tournament game's result. Many of these, played
  in parallel, are what the "colosseum" grid shows simultaneously.
- :class:`GenerationRecord` / :class:`RunRecord` — the whole run, JSON-dumpable.

Nothing here is faked or embellished: every field is filled from an actual game
or an actual breeding event (honesty rule in PROJECT_GUIDE.md).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class MutationEvent:
    """A single gene mutation: ``gene`` changed from ``before`` to ``after``."""

    gene: str
    before: float
    after: float


@dataclass
class BreedingRecord:
    """Two parents crossing over (+ mutation) into one child."""

    child_id: str
    parent_a_id: str
    parent_a_vector: list[float]
    parent_b_id: str
    parent_b_vector: list[float]
    crossover_mask: list[int]      # per gene: 0 = from A, 1 = from B
    mutations: list[MutationEvent]
    child_vector: list[float]


@dataclass
class GameRecord:
    """The result of one tournament game (metadata; moves optional).

    ``fens`` / ``evals`` are filled only when move-logging is on — they let the
    Phase 3 "colosseum" replay each game position-by-position with a live eval
    bar, entirely from static data (no engine needed in the browser).
    """

    white_id: str
    black_id: str
    result: str            # "1-0" | "0-1" | "1/2-1/2"
    plies: int
    termination: str
    pgn: str | None = None       # filled only when PGN logging is on (heavier)
    fens: list[str] | None = None    # one FEN per ply (incl. start position)
    evals: list[int] | None = None   # White-perspective centipawns per FEN


@dataclass
class GenerationRecord:
    """A snapshot of one generation: who lived, who bred, how strong the best is."""

    index: int
    best_id: str
    best_vector: list[float]
    best_fitness: float
    benchmark_winrate: float        # best genome vs the fixed baseline (the curve)
    population: list[dict]          # [{id, vector, fitness}, ...]
    breedings: list[BreedingRecord] = field(default_factory=list)
    games: list[GameRecord] = field(default_factory=list)


@dataclass
class RunRecord:
    """A whole evolution run — the top-level artifact the frontend reads."""

    config: dict
    generations: list[GenerationRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def write_run(run: RunRecord, directory: str | Path) -> Path:
    """Write the run artifacts to ``directory`` and return that path.

    Produces:
      - ``run.json``        — the full run (config + every generation).
      - ``strength.csv``    — generation, best_fitness, benchmark_winrate.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    (directory / "run.json").write_text(
        json.dumps(run.to_dict(), indent=2), encoding="utf-8"
    )

    lines = ["generation,best_fitness,benchmark_winrate"]
    for g in run.generations:
        lines.append(f"{g.index},{g.best_fitness:.3f},{g.benchmark_winrate:.3f}")
    (directory / "strength.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return directory
