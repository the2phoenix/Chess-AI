"""Build the Phase 4 difficulty ladder (`web/opponents.json`) from a GA run.

"Play vs Trained AI" means facing the *evolved* genome, not the hand-tuned
default. This turns a finished run (``web/showcase.json``) into a ladder of
opponents from a barely-evolved Generation-0 genome up to the deep-thinking
champion. Difficulty ramps on two honest axes: a weaker vs stronger *evolved*
genome, and shallow vs deep *search*.

Usage:
    python make_opponents.py                       # reads web/showcase.json
    python make_opponents.py --in web/showcase.json --out web/opponents.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"


def build_ladder(showcase: dict) -> list[dict]:
    gens = showcase["generations"]
    champion = showcase["best"]["vector"]
    champion_gen = showcase["best"]["id"]
    gen0 = gens[0]["best_vector"]
    gen0_wr = gens[0]["benchmark_winrate"]
    champ_wr = max(g["benchmark_winrate"] for g in gens)

    # Each rung: (id, label, genome, depth, blurb). Difficulty climbs by using a
    # stronger evolved genome and/or a deeper search.
    return [
        {
            "id": "hatchling",
            "label": "Hatchling — Gen 0, shallow",
            "genome": gen0,
            "depth": 1,
            "blurb": f"Generation 0's best genome ({gen0_wr*100:.0f}% vs baseline), "
                     f"looking just one move ahead. Beatable.",
        },
        {
            "id": "fledgling",
            "label": "Fledgling — Gen 0, deeper",
            "genome": gen0,
            "depth": 2,
            "blurb": "The same early genome, but now thinking two plies ahead.",
        },
        {
            "id": "adept",
            "label": "Adept — Champion, fast",
            "genome": champion,
            "depth": 2,
            "blurb": "The evolved champion's weights, playing quickly.",
        },
        {
            "id": "veteran",
            "label": "Veteran — Champion",
            "genome": champion,
            "depth": 3,
            "blurb": "The champion at full default depth.",
        },
        {
            "id": "champion",
            "label": "Champion — deep",
            "genome": champion,
            "depth": 4,
            "blurb": f"The fully evolved champion ({champ_wr*100:.0f}% vs baseline, "
                     f"from {champion_gen}), thinking hard.",
        },
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build web/opponents.json from a GA run")
    parser.add_argument("--in", dest="inp", type=str, default=str(WEB / "showcase.json"))
    parser.add_argument("--out", type=str, default=str(WEB / "opponents.json"))
    parser.add_argument("--default-id", default="veteran",
                        help="which rung is selected by default in the UI")
    args = parser.parse_args(argv)

    inp = Path(args.inp)
    if not inp.exists():
        print(f"error: {inp} not found — run showcase_data.py first.", file=sys.stderr)
        return 1

    showcase = json.loads(inp.read_text(encoding="utf-8"))
    ladder = build_ladder(showcase)
    payload = {
        "gene_names": showcase.get("gene_names"),
        "default": args.default_id,
        "opponents": ladder,
    }
    out = Path(args.out)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out} — {len(ladder)} opponents "
          f"({', '.join(o['id'] for o in ladder)}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
