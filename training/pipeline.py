"""The continual-learning pipeline (Phase 8 / GSD §3) — the day/night loop.

    collect  ->  train  ->  deploy (if stronger)  ->  repeat

- **collect**: the deployed champion plays self-play games (with move variety so
  they differ) into the growing experience pool. *(Your "morning: many games
  played".)*
- **train**: a GA evolution, **warm-started from the champion** and grounded in
  **openings sampled from the pool**, breeds a candidate. It is **promoted to a
  new deployed version only if it beats the incumbent by a margin** (gating), so
  strength is monotonic and honest — improvement is periodic and offline, never
  "instantly superhuman after one game" (GSD). *(Your "night: data trained".)*
- **status**: pool composition + deployed version history.
- **cycle**: one collect + train (a full day/night turn).

Honest by construction: heavy compute is offline (this script), the frontend
only ever reads the resulting artifacts. Defaults are small/laptop-friendly;
the *same code* runs the big job on Colab (just larger numbers + ``--kind nn``).

Examples::

    python pipeline.py status
    python pipeline.py collect --games 20 --depth 2
    python pipeline.py train --generations 6 --population 12 --gate 0.53
    python pipeline.py cycle --games 20 --generations 6
    python pipeline.py train --kind nn --deploy-web      # NN job, push to viewer
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import chess

from engine import Engine, Genome, NNGenome, DEFAULT_GENOME, NN_PARAMS, is_game_over
from chess_io import save_pgn
from experience_pool import ExperiencePool, DEFAULT_ROOT as POOL_ROOT
from ga.evolution import EvolutionConfig, evolve
from ga.tournament import benchmark, make_openings
import deploy

ROOT = Path(__file__).resolve().parent
DEPLOY_ROOT = deploy.DEFAULT_ROOT
WEB_DIR = ROOT.parent / "web"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _base_for_kind(kind: str, deploy_root):
    """The fixed reference genome for a *fresh* pool (no champion yet).

    Scalar -> the hand-tuned default. NN -> the zero net, which under the
    residual design ≈ the handcrafted eval, so the loop starts at baseline.
    """
    champ = deploy.current_champion(deploy_root)
    if champ is not None:
        return deploy.current_genome(deploy_root)
    if kind == "nn":
        return NNGenome.from_vector([0.0] * NN_PARAMS), "nn"
    return DEFAULT_GENOME, "scalar"


def _random_opening(rng: random.Random, plies: int) -> list[str]:
    board = chess.Board()
    moves = []
    for _ in range(plies):
        legal = list(board.legal_moves)
        if not legal:
            break
        mv = rng.choice(legal)
        board.push(mv)
        moves.append(mv.uci())
    return moves


def _self_play_game(genome, depth: int, rng: random.Random, max_plies: int) -> chess.Board:
    """One champion-vs-champion game with move variety, from a random opening."""
    white = Engine(genome=genome, depth=depth, name="self-W", random_margin=40)
    black = Engine(genome=genome, depth=depth, name="self-B", random_margin=40)
    white._rng = random.Random(rng.random())
    black._rng = random.Random(rng.random())

    board = chess.Board()
    for uci in _random_opening(rng, rng.randint(2, 4)):
        board.push(chess.Move.from_uci(uci))
    while not is_game_over(board) and len(board.move_stack) < max_plies:
        eng = white if board.turn == chess.WHITE else black
        mv = eng.select_move(board)
        if mv is None:
            break
        board.push(mv)
    return board


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_collect(args) -> int:
    pool = ExperiencePool(args.pool)
    genome, kind = _base_for_kind(args.kind, args.deploy)
    rng = random.Random(args.seed)
    print(f"Collecting {args.games} self-play games "
          f"(kind={kind}, depth={args.depth}) into {pool.root} ...")
    for i in range(1, args.games + 1):
        board = _self_play_game(genome, args.depth, rng, args.max_plies)
        entry = pool.add_board(board, source="self_play",
                               white="Champion", black="Champion")
        print(f"  game {i:>3}/{args.games}: {entry.result:<7} "
              f"{entry.plies} plies  -> {entry.id}")
    stats = pool.stats()
    print(f"Pool now holds {stats['total']} games {stats['by_source']}.")
    return 0


def cmd_train(args) -> int:
    pool = ExperiencePool(args.pool)
    base_genome, kind = _base_for_kind(args.kind, args.deploy)
    rng = random.Random(args.seed)

    # Ground evolution in positions that actually occur: sample openings from
    # the pool; fall back to synthetic ones if the pool is too small.
    openings = pool.sample_openings(args.benchmark_openings, plies=args.opening_plies, rng=rng)
    grounded = bool(openings)
    if not openings:
        openings = make_openings(args.benchmark_openings, seed=args.seed + 999)

    print(f"Training: kind={kind}, pop={args.population}, gen={args.generations}, "
          f"depth={args.depth}")
    print(f"  warm-started from the current champion; "
          f"{'pool-sampled' if grounded else 'synthetic'} openings "
          f"({len(openings)}); pool size {pool.size()}.")

    cfg = EvolutionConfig(
        population=args.population,
        generations=args.generations,
        depth=args.depth,
        max_plies=args.max_plies,
        benchmark_openings=args.benchmark_openings,
        processes=args.processes,
        seed=args.seed,
        genome_kind=kind,
        seed_genome=base_genome.to_vector(),
        openings=openings,
    )
    result = evolve(cfg)
    candidate = result.best.genome

    # Gate: the candidate must beat the *incumbent* champion by a margin.
    winrate_vs_incumbent = benchmark(
        candidate, base_genome, openings, depth=args.depth,
        max_plies=args.max_plies, processes=args.processes,
    )
    winrate_vs_default = benchmark(
        candidate, DEFAULT_GENOME if kind == "scalar" else NNGenome.from_vector([0.0] * NN_PARAMS),
        openings, depth=args.depth, max_plies=args.max_plies, processes=args.processes,
    )
    print(f"\nCandidate vs incumbent: {winrate_vs_incumbent*100:.1f}%  "
          f"(gate {args.gate*100:.0f}%)")
    print(f"Candidate vs baseline : {winrate_vs_default*100:.1f}%")

    if winrate_vs_incumbent > args.gate:
        entry = deploy.promote(
            args.deploy, kind, candidate.to_vector(),
            benchmark_winrate=winrate_vs_default,
            vs_incumbent=winrate_vs_incumbent,
            source_games=pool.size(),
            notes=f"trained on {pool.size()} pooled games",
        )
        print(f"PROMOTED -> deployed v{entry['version']} "
              f"({winrate_vs_incumbent*100:.1f}% vs incumbent).")
        if args.deploy_web:
            _deploy_web(kind, candidate)
    else:
        print("Not promoted - candidate did not clear the gate. Incumbent stays.")
    return 0


def cmd_status(args) -> int:
    pool = ExperiencePool(args.pool)
    stats = pool.stats()
    print("Experience pool")
    print(f"  total games : {stats['total']}  {stats['by_source']}")
    print(f"  location    : {stats['root']}")

    reg = deploy.load_registry(args.deploy)
    print("\nDeployed engine versions")
    if not reg["versions"]:
        print("  (none yet - the loop starts from the hand-tuned default)")
    else:
        for v in reg["versions"]:
            marker = " <- current" if v["version"] == reg["current"] else ""
            print(f"  v{v['version']:<2} {v['kind']:<6} "
                  f"vs-baseline {v['benchmark_winrate']*100:>5.1f}%  "
                  f"vs-incumbent {v['vs_incumbent']*100:>5.1f}%  "
                  f"({v['source_games']} games, {v['created_at']}){marker}")
    return 0


def cmd_cycle(args) -> int:
    print("=== day/night cycle: collect, then train ===\n")
    rc = cmd_collect(args)
    if rc != 0:
        return rc
    print()
    return cmd_train(args)


def _deploy_web(kind: str, genome) -> None:
    """Push an NN champion to the viewer (it auto-loads web/nn_weights.json)."""
    if kind != "nn":
        print("  (--deploy-web: scalar champions are served via opponents.json; "
              "run make_opponents.py to refresh the ladder.)")
        return
    import json
    path = WEB_DIR / "nn_weights.json"
    path.write_text(json.dumps(genome.to_dict()), encoding="utf-8")
    print(f"  deployed to viewer: {path}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Darwin's Gambit continual pipeline")
    parser.add_argument("--pool", default=str(POOL_ROOT), help="experience-pool directory")
    parser.add_argument("--deploy", default=str(DEPLOY_ROOT),
                        help="deployed-version registry directory (use separate "
                             "dirs for scalar vs nn so experiments stay separate)")
    parser.add_argument("--kind", default="scalar", choices=["scalar", "nn"],
                        help="genome kind for a fresh pool (ignored once a champion is deployed)")
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--max-plies", type=int, default=140, dest="max_plies")
    parser.add_argument("--processes", type=int, default=None)
    parser.add_argument("--seed", type=int, default=0)
    sub = parser.add_subparsers(dest="command", required=True)

    pc = sub.add_parser("collect", help="self-play games into the pool")
    pc.add_argument("--games", type=int, default=20)
    pc.set_defaults(func=cmd_collect)

    pt = sub.add_parser("train", help="evolve on the pool; promote if stronger")
    pt.add_argument("--population", type=int, default=12)
    pt.add_argument("--generations", type=int, default=6)
    pt.add_argument("--benchmark-openings", type=int, default=8, dest="benchmark_openings")
    pt.add_argument("--opening-plies", type=int, default=8, dest="opening_plies")
    pt.add_argument("--gate", type=float, default=0.53, help="min win-rate vs incumbent to promote")
    pt.add_argument("--deploy-web", action="store_true", help="push an NN champion to the viewer")
    pt.set_defaults(func=cmd_train)

    ps = sub.add_parser("status", help="pool + deployed-version summary")
    ps.set_defaults(func=cmd_status)

    pcy = sub.add_parser("cycle", help="one collect + train (a full day/night turn)")
    pcy.add_argument("--games", type=int, default=20)
    pcy.add_argument("--population", type=int, default=12)
    pcy.add_argument("--generations", type=int, default=6)
    pcy.add_argument("--benchmark-openings", type=int, default=8, dest="benchmark_openings")
    pcy.add_argument("--opening-plies", type=int, default=8, dest="opening_plies")
    pcy.add_argument("--gate", type=float, default=0.53)
    pcy.add_argument("--deploy-web", action="store_true")
    pcy.set_defaults(func=cmd_cycle)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
