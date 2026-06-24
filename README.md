# Darwin's Gambit ♟️

> A chess engine that **teaches itself to play** through neuroevolution and self-play — no opening books, no human games, no pre-trained data. It starts knowing only the rules and evolves.

---

## What it is

A web app with three things to do:

1. **Watch AI vs AI** — two engines battle, with a live evaluation bar and clocks, playing a fresh game each time.
2. **Play vs the Trained AI** — face the evolved engine on a difficulty ladder (a Gen-0 "hatchling" up to the deep-thinking champion, plus an optional evolved neural net).
3. **Play vs the Adaptive AI** — a strong base engine that *also* studies *your* habits and gets harder the more you play it (the base engine is never weakened).

Under the hood, a genetic algorithm evolves a position-evaluation function — either five handcrafted weights or a small neural network — purely through self-play tournaments. Engines play, winners breed and mutate, and over generations the population gets stronger: natural selection applied to chess intuition. A continual pipeline keeps the loop going — games collect into an experience pool, periodic offline training refines the engine, and a stronger champion is deployed only if it beats the incumbent.

## Honest scope

This is **not** an attempt at an unbeatable, superhuman engine — that needs data-center-scale compute. This is a **self-improving system that demonstrably gets stronger the more it plays**, with a measurable strength curve to prove it. That honest, rigorous result is the whole point.

## Status

**Build complete — all phases shipped** (engine → GA → showcase → play-vs-trained → auth → NN evaluator → adaptive opponent → continual pipeline). 45 tests across 5 suites. See `CHANGELOG.md`.

## Tech stack

| Layer | Tech |
|---|---|
| Engine + training (offline) | Python, python-chess, NumPy, multiprocessing |
| Training compute | Google Colab (free, CPU) — `notebooks/day_night_pipeline.ipynb` |
| Frontend + local viewer | Stdlib Python HTTP server + vanilla HTML/CSS/JS (no build step) |
| Auth + data | Supabase (Postgres + Auth) with Row-Level Security |
| Data interchange | JSON (weights), PGN (games) |

## Architecture

**Heavy work is offline.** Evolution and self-play run on a cloud machine (or your laptop) and produce small JSON artifacts (`weights.json`, `nn_weights.json`, `showcase.json`, PGN). The **frontend is light** — the static Showcase reads those artifacts directly; live play calls the Python engine (locally via `web/server.py`, or a small backend in production).

## Run it locally

Requires Python 3.10+ (`pip install -r training/requirements.txt`).

```bash
# Local viewer — Play vs Engine, Watch AI vs AI, Adaptive mode, Showcase
cd web
python server.py            # opens http://localhost:8000

# Engine sanity (Phase 1): one legal self-play game
cd training && python selfplay.py --depth 2

# Evolution strength curve (Phase 2)
python evolve.py

# Adaptive opponent demo (Phase 7)
python adaptive_demo.py --sessions 5

# Continual day/night pipeline (Phase 8)
python pipeline.py status
python pipeline.py --depth 2 collect --games 10
python pipeline.py --depth 2 train --population 12 --generations 5

# Tests
python tests/test_engine.py && python tests/test_ga.py && python tests/test_nn.py \
  && python tests/test_opponent_model.py && python tests/test_pipeline.py
```

Showcase: <http://localhost:8000/showcase> (Colosseum · Tournament of Champions · Genomes Bonding · Evolution & Analytics).

## Cloud training (day/night loop)

Upload `training.zip` to `notebooks/day_night_pipeline.ipynb` on Google Colab and run the cells: it auto-repeats `collect → train → deploy` (scalar first to validate, then the neural net for the real grind), and hands back a `nn_weights.json` to drop into `web/`.

## Project structure

```
/training        Python: engine, GA, NN evaluator, opponent model, pipeline (offline)
/web             Frontend + local viewer + Supabase auth
/supabase        Database schema + RLS policies
/notebooks       Colab training notebooks
PRD.md TRD.md GSD.md UIUX.md   Product & system docs
PROJECT_GUIDE.md        Project context + rules
CHANGELOG.md     Version history
```

## Documentation

- `PRD.md` — what we're building and why
- `TRD.md` — technical requirements, stack, data model
- `GSD.md` — system design: engine, GA, adaptive model, continual pipeline
- `UIUX.md` — interface and experience design
- `PROJECT_GUIDE.md` — how to work in this repo

## Configuration

Copy `web/supabase-config.example.js` to `web/supabase-config.js` and fill in your Supabase URL + publishable (anon) key. The service-role key is **never** used in the browser. Secrets stay out of git (see `.gitignore`).
