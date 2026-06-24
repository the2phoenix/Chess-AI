"""Tournament-of-Champions — a knockout bracket where winners absorb losers.

Each match is one game between two genomes; the winner advances. In every round
*except the final*, the winner then **absorbs** the loser (winner-dominant
crossover + a little mutation) into a stronger hybrid that goes on to the next
round. The field halves until two remain; they fight, and that winner is the
ultimate champion.

This reuses the GA's match player and genetic operators, and records everything
(each game's move trace + each merge's lineage) so the showcase can replay the
bracket and animate the merges from real data.
"""

from __future__ import annotations

import random
from dataclasses import asdict

import chess

from engine import Genome
from engine.evaluation import PIECE_VALUES

from .match import play_match, trace_game
from .genome_ops import mutate


def _material_balance(board: chess.Board) -> int:
    bal = 0
    for piece in board.piece_map().values():
        v = PIECE_VALUES[piece.piece_type]
        bal += v if piece.color == chess.WHITE else -v
    return bal


def biased_crossover(
    winner: Genome, loser: Genome, rng: random.Random, winner_bias: float = 0.7
) -> tuple[Genome, list[int]]:
    """Winner-dominant uniform crossover: each gene comes from the winner with
    probability ``winner_bias``, else the loser. Returns child + mask (0=winner,
    1=loser) so the absorb can be animated."""
    wv, lv = winner.to_vector(), loser.to_vector()
    mask = [0 if rng.random() < winner_bias else 1 for _ in wv]
    child = [lv[i] if mask[i] else wv[i] for i in range(len(wv))]
    return Genome.from_vector(child), mask


def _play_bracket_match(a: Genome, b: Genome, depth: int, max_plies: int):
    """One decisive game: returns (result, winner 'a'|'b', fens, evals)."""
    outcome = play_match(a, b, depth=depth, max_plies=max_plies)
    fens, evals = trace_game(outcome.board)
    if outcome.result == "1-0":
        winner = "a"
    elif outcome.result == "0-1":
        winner = "b"
    else:
        # Draw → decide by final material, else the higher seed (a).
        winner = "a" if _material_balance(outcome.board) >= 0 else "b"
    return outcome.result, winner, fens, evals


def run_knockout(
    seeds: list[dict],
    depth: int = 2,
    max_plies: int = 120,
    winner_bias: float = 0.7,
    mutation_rate: float = 0.2,
    mutation_sigma: float = 0.2,
    seed: int = 0,
) -> dict:
    """Run the bracket. ``seeds`` is a list of ``{id, vector, label}`` (ideally a
    power of two). Returns a dict with ``rounds`` and ``champion``."""
    rng = random.Random(seed)
    current = [{"id": s["id"], "vector": s["vector"], "label": s.get("label", s["id"])}
               for s in seeds]
    rounds = []
    round_no = 0

    while len(current) > 1:
        is_final = len(current) == 2
        matches = []
        advancers = []
        for i in range(0, len(current) - 1, 2):
            a, b = current[i], current[i + 1]
            result, who, fens, evals = _play_bracket_match(
                Genome.from_vector(a["vector"]), Genome.from_vector(b["vector"]),
                depth, max_plies,
            )
            win, lose = (a, b) if who == "a" else (b, a)
            match = {
                "a": a, "b": b, "result": result, "winner_id": win["id"],
                "fens": fens, "evals": evals,
            }
            if is_final:
                match["champion_id"] = win["id"]
                advancers.append({"id": win["id"], "vector": win["vector"], "label": win["label"]})
            else:
                child, mask = biased_crossover(
                    Genome.from_vector(win["vector"]), Genome.from_vector(lose["vector"]),
                    rng, winner_bias,
                )
                child, muts = mutate(child, rng, mutation_rate, mutation_sigma)
                child_id = f"r{round_no + 1}-{len(advancers)}"
                match["merge"] = {
                    "winner_id": win["id"], "winner_label": win["label"], "winner_vector": win["vector"],
                    "loser_id": lose["id"], "loser_label": lose["label"], "loser_vector": lose["vector"],
                    "crossover_mask": mask,
                    "mutations": [asdict(m) for m in muts],
                    "child_id": child_id, "child_vector": child.to_vector(),
                }
                advancers.append({"id": child_id, "vector": child.to_vector(),
                                  "label": win["label"] + "+"})
            matches.append(match)

        if len(current) % 2 == 1:  # odd one out gets a bye
            advancers.append(current[-1])

        rounds.append({"round": round_no, "is_final": is_final, "matches": matches})
        current = advancers
        round_no += 1

    return {"rounds": rounds, "champion": current[0] if current else None}
