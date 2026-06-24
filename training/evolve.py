"""Run the Phase 2 genetic algorithm — evolve the evaluation weights by self-play.

This is the Phase 2 acceptance check: it prints a **strength curve** (the best
genome's win-rate against the fixed hand-tuned baseline, per generation). If the
GA is working, that number trends up and the final evolved genome beats the
baseline.

Usage:
    python evolve.py                          # quick smoke run (small)
    python evolve.py --population 24 --generations 30 --processes 8
    python evolve.py --depth 2 --out runs/run1   # write run.json + strength.csv
    python evolve.py --weights weights.json      # also save the best genome

All compute is offline/local (multiprocessing tournaments). Never run this in a
web function — it would time out.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from engine import DEFAULT_GENOME
from ga import evolve, EvolutionConfig, write_run
from ga.lineage import GenerationRecord


def _bar(value: float, width: int = 24) -> str:
    filled = int(round(value * width))
    return "#" * filled + "." * (width - filled)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Darwin's Gambit — evolve evaluation weights")
    parser.add_argument("--population", type=int, default=12)
    parser.add_argument("--generations", type=int, default=8)
    parser.add_argument("--depth", type=int, default=2, help="search depth during evolution (shallow!)")
    parser.add_argument("--max-plies", type=int, default=160)
    parser.add_argument("--elite", type=int, default=2)
    parser.add_argument("--mutation-rate", type=float, default=0.3)
    parser.add_argument("--mutation-sigma", type=float, default=0.25)
    parser.add_argument("--benchmark-openings", type=int, default=6)
    parser.add_argument("--processes", type=int, default=os.cpu_count(),
                        help="parallel game workers (default: all cores)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--nn", action="store_true",
                        help="evolve the neural-net evaluator (Phase 6) instead of the 5 scalar weights")
    parser.add_argument("--log-games", action="store_true", help="store every game's PGN (heavier)")
    parser.add_argument("--out", type=str, default=None, help="directory for run.json + strength.csv")
    parser.add_argument("--weights", type=str, default=None, help="path to save the best genome JSON")
    args = parser.parse_args(argv)

    cfg = EvolutionConfig(
        population=args.population,
        generations=args.generations,
        depth=args.depth,
        max_plies=args.max_plies,
        elite=args.elite,
        mutation_rate=args.mutation_rate,
        mutation_sigma=args.mutation_sigma,
        benchmark_openings=args.benchmark_openings,
        processes=args.processes,
        seed=args.seed,
        log_games=args.log_games,
        genome_kind="nn" if args.nn else "scalar",
    )

    print("Darwin's Gambit - Phase 2 evolution")
    print(f"  population={cfg.population}  generations={cfg.generations}  "
          f"depth={cfg.depth}  processes={cfg.processes}  seed={cfg.seed}")
    print(f"  baseline = DEFAULT_GENOME {DEFAULT_GENOME.to_vector()}")
    print("\n  gen | best fitness | win-rate vs baseline")
    print("  ----+--------------+" + "-" * 34)

    def report(rec: GenerationRecord) -> None:
        wr = rec.benchmark_winrate
        flag = "  <- beats baseline" if wr > 0.5 else ""
        print(f"  {rec.index:>3} |   {rec.best_fitness:>8.1f}   | "
              f"{_bar(wr)} {wr*100:5.1f}%{flag}")

    result = evolve(cfg, on_generation=report)

    best = result.best
    if args.nn:
        print(f"\nBest NN evaluator evolved — {len(best.genome.to_vector())} weights, "
              f"benchmarked vs the hand-tuned scalar eval.")
    else:
        print("\nBest genome found:")
        for name, value in zip(_gene_names(), best.genome.to_vector()):
            print(f"  {name:<14} {value:.3f}")
    final_wr = result.run.generations[-1].benchmark_winrate
    print(f"\nFinal-generation best win-rate vs baseline: {final_wr*100:.1f}%")

    # Persist artifacts.
    out_dir = Path(args.out) if args.out else Path("runs") / datetime.now().strftime("%Y%m%d-%H%M%S")
    write_run(result.run, out_dir)
    print(f"\nRun written to {out_dir}/ (run.json, strength.csv)")

    weights_path = Path(args.weights) if args.weights else out_dir / "weights.json"
    weights_path.parent.mkdir(parents=True, exist_ok=True)
    weights_path.write_text(json.dumps(best.genome.to_dict(), indent=2), encoding="utf-8")
    print(f"Best genome saved to {weights_path}")

    return 0


def _gene_names() -> list[str]:
    from ga import GENE_NAMES
    return GENE_NAMES


if __name__ == "__main__":
    sys.exit(main())
