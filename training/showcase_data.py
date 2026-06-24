"""Generate the Phase 3 showcase data (`web/showcase.json`).

Runs a small evolution with full move-logging, then writes a single static JSON
the showcase frontend replays — the "colosseum" (every game, position-by-position
with an eval bar), the "genomes bonding" animation (real crossover lineage), and
the strength curve. No engine runs in the browser: the showcase reads only this
file, so it deploys to a static host (Vercel) unchanged.

Usage:
    python showcase_data.py                       # small, quick demo run
    python showcase_data.py --population 8 --generations 8 --processes 8
    python showcase_data.py --out ../web/showcase.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from engine import DEFAULT_GENOME
from ga import evolve, EvolutionConfig, GENE_NAMES
from ga.lineage import GenerationRecord


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate web/showcase.json from a GA run")
    parser.add_argument("--population", type=int, default=6)
    parser.add_argument("--generations", type=int, default=6)
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--max-plies", type=int, default=80,
                        help="cap per game (keeps the showcase JSON small)")
    parser.add_argument("--processes", type=int, default=os.cpu_count())
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=str, default=str(Path(__file__).resolve().parent.parent / "web" / "showcase.json"))
    args = parser.parse_args(argv)

    cfg = EvolutionConfig(
        population=args.population,
        generations=args.generations,
        depth=args.depth,
        max_plies=args.max_plies,
        processes=args.processes,
        seed=args.seed,
        log_moves=True,   # the whole point: record every game's frames
    )

    print("Generating showcase data...")
    print(f"  population={cfg.population}  generations={cfg.generations}  "
          f"depth={cfg.depth}  processes={cfg.processes}")

    def report(rec: GenerationRecord) -> None:
        print(f"  gen {rec.index}: best fitness {rec.best_fitness:.1f}, "
              f"win-rate vs baseline {rec.benchmark_winrate*100:.1f}%, "
              f"{len(rec.games)} games logged")

    result = evolve(cfg, on_generation=report)

    payload = {
        "gene_names": GENE_NAMES,
        "baseline": DEFAULT_GENOME.to_vector(),
        "config": result.run.config,
        "best": {
            "id": result.best.id,
            "vector": result.best.genome.to_vector(),
            "fitness": result.best.fitness,
        },
        "generations": [asdict(g) for g in result.run.generations],
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload), encoding="utf-8")
    size_kb = out.stat().st_size / 1024
    total_games = sum(len(g.games) for g in result.run.generations)
    print(f"\nWrote {out} ({size_kb:.0f} KB) — {len(result.run.generations)} "
          f"generations, {total_games} games.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
