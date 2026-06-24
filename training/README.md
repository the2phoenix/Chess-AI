# training/ — Darwin's Gambit engine (offline Python)

The offline, heavy half of the project: the chess engine and (later) the genetic
algorithm that evolves it. The deployed web frontend never runs this code — it
only reads the small artifacts (`weights.json`, PGN) this side produces.

## Status: Phase 1 (Engine MVP) ✅

What exists now:

- **Search** (`engine/search.py`) — minimax with alpha-beta pruning, iterative
  deepening, move ordering, and depth-adjusted mate scores. This is the *fixed*
  half of the engine; it never evolves.
- **Evaluation** (`engine/evaluation.py`) — a handcrafted, weighted sum of
  features (material, piece-square tables, mobility, king safety, pawn
  structure). The weight vector is a `Genome` — deliberately structured so
  Phase 2's GA can evolve it. No human opening theory or game data is used.
- **Engine** (`engine/engine.py`) — wraps search + evaluation behind a small API
  (`select_move`, `analyse`, `eval_bar_score`).
- **chess_io** (`chess_io/`) — PGN export (JSON for weights, PGN for games).

## Setup

```bash
cd training
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

## Try it

Watch the engine play itself a full, legal game (the Phase 1 acceptance check):

```bash
python selfplay.py                 # depth-3 game, prints the move list + PGN
python selfplay.py --depth 2 --quiet
python selfplay.py --time 0.5      # 0.5s/move via iterative deepening
python selfplay.py --pgn games/demo.pgn
```

Play against it yourself:

```bash
python play.py                     # you are White
python play.py --color black --depth 4
```

## Tests

```bash
python -m pytest -q                # if pytest is installed
python tests/test_engine.py        # or run directly, no pytest needed
```

The tests assert the engine only ever plays legal moves, finds a mate-in-one,
grabs a hanging queen, and that the evaluation is material-sane and
colour-symmetric.

## Layout

```
engine/
  evaluation.py   handcrafted eval + the evolvable Genome (weights)
  search.py       minimax + alpha-beta + iterative deepening (fixed)
  engine.py       Engine class tying eval + search together
chess_io/
  pgn.py          record games as PGN
selfplay.py       engine-vs-engine demo (Phase 1 acceptance check)
play.py           human-vs-engine terminal CLI
tests/
  test_engine.py  legality + tactics + eval + genome tests
```

## What's next (not built yet)

Phase 2 — a genetic algorithm that evolves the `Genome` weights through
self-play tournaments, producing a rising strength curve. See `../PROJECT_GUIDE.md`
build order. Phase 1 stops here, on purpose, so the engine can be verified first.
```
