"""Generate the Tournament-of-Champions bracket (`web/tournament.json`).

Evolves a population, then takes **each generation's champion** as a bracket
seed (Gen 0 … Gen N) and runs a knockout where winners absorb losers into
hybrids until one ultimate champion remains. Records each match's move trace and
each merge's lineage so the showcase can replay the bracket and animate the
merges from real data.

For a clean bracket, run with a power-of-two number of generations (default 8).

Usage:
    python tournament_data.py                       # 8 generations → 8 seeds
    python tournament_data.py --population 10 --generations 8 --processes 8
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from ga import evolve, EvolutionConfig, run_knockout, GENE_NAMES

WEB = Path(__file__).resolve().parent.parent / "web"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate web/tournament.json")
    parser.add_argument("--population", type=int, default=10)
    parser.add_argument("--generations", type=int, default=8, help="also the # of bracket seeds")
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--max-plies", type=int, default=120)
    parser.add_argument("--processes", type=int, default=os.cpu_count())
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--out", type=str, default=str(WEB / "tournament.json"))
    args = parser.parse_args(argv)

    print("Evolving a population for the tournament…")
    result = evolve(EvolutionConfig(
        population=args.population, generations=args.generations,
        depth=args.depth, max_plies=args.max_plies,
        processes=args.processes, seed=args.seed,
    ))

    # One seed per generation: that generation's champion.
    seeds = [
        {"id": g.best_id, "vector": g.best_vector, "label": f"Gen {g.index}",
         "winrate": g.benchmark_winrate}
        for g in result.run.generations
    ]
    print(f"Seeded {len(seeds)} generation-champions; running the knockout…")

    bracket = run_knockout(seeds, depth=args.depth, max_plies=args.max_plies, seed=args.seed)

    payload = {
        "gene_names": GENE_NAMES,
        "seeds": seeds,
        "rounds": bracket["rounds"],
        "champion": bracket["champion"],
    }
    out = Path(args.out)
    out.write_text(json.dumps(payload), encoding="utf-8")
    n_matches = sum(len(r["matches"]) for r in bracket["rounds"])
    champ = bracket["champion"]
    print(f"\nWrote {out} ({out.stat().st_size/1024:.0f} KB) — "
          f"{len(bracket['rounds'])} rounds, {n_matches} matches.")
    print(f"Ultimate champion: {champ['label']} ({champ['id']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
