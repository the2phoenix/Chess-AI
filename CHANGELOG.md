# Changelog

All notable changes to Darwin's Gambit are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/); this project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]
### Added — Deployment readiness + day/night Colab notebook
- `notebooks/day_night_pipeline.ipynb`: a Colab notebook that runs the continual
  loop as **auto-repeating cycles in one cell** — scalar first (fast, validates
  the loop), then the neural net (the real grind). Scalar and NN use **separate
  pools + deploy registries** so the experiments never mix; optional Drive mount
  persists state across sessions; output streams live.
- The engine server is now **deploy-ready** without changing local behaviour:
  `web/server.py` reads `PORT`/`HOST` from the environment (binds `0.0.0.0` when
  hosted), sends **CORS** headers (origin via `DARWIN_CORS_ORIGIN`, default `*`),
  and answers preflight `OPTIONS`. The frontend `api()` honours
  `window.DARWIN_API_BASE` (new public `web/app-config.js`) so the static site
  can call a separate engine backend; empty = same-origin (local unchanged).
- `render.yaml` (engine API on Render), `web/vercel.json` (static frontend +
  `/showcase` route), and `DEPLOY.md` (full Vercel + Render walkthrough,
  GitHub push, Supabase-in-prod notes, and honest free-tier caveats).
- `pipeline.py` gained a `--deploy` flag (separate registry dirs per experiment).
  README rewritten for the finished build; `training/runs/` now gitignored.

### Added — V2 Phase 8: continual experience-pool pipeline (`experience_pool.py`, `pipeline.py`, `deploy.py`)
- The day/night loop, `collect → train → deploy → repeat` (GSD §3), all offline:
  - `experience_pool.py` — one growing on-disk pool of games fed by **two
    sources**: self-play (the `collect` step) and **human play** (the viewer
    posts finished games to a new `/api/pool_add`). Each game is stored as a
    per-game JSON record (metadata + UCI moves + PGN) with a lightweight
    manifest index. `sample_openings()` draws real opening lines from the pool
    so evolution is grounded in positions that actually occur.
  - `deploy.py` — a versioned champion registry (the local mirror of TRD
    `engine_versions`): `promote()` appends a new version and makes it current;
    `current_genome()` reconstructs the deployed champion (or the hand-tuned
    default when nothing is deployed yet).
  - `pipeline.py` — the orchestrator/CLI: `collect` (self-play → pool, with move
    variety), `train` (a GA **warm-started from the champion** and run on
    **pool-sampled openings**, **promoted only if it beats the incumbent by a
    margin** — gating keeps deployed strength monotonic and honest), `status`,
    and `cycle` (one collect+train). `--kind nn` + `--deploy-web` run the NN job
    and push the champion straight to the viewer. The *same code* scales up on
    Colab — only the numbers change.
- **Warm-start added to evolution** (`ga/evolution.py`): `EvolutionConfig`
  gained `seed_genome` (gen-0 is the champion + mutated copies of it, so
  evolution resumes from deployed strength) and `openings` (inject the pool's
  lines). Scalar and NN both supported.
- Verified end-to-end: a real run collected varied self-play games, then a
  warm-started, pool-grounded evolution produced a candidate that beat the
  incumbent 78.1%, cleared the gate, and was promoted to deployed v1. Tests in
  `tests/test_pipeline.py` (pool add/sample/persist, registry promote/load, and
  a full collect→train→gated-promote cycle). 45 tests now pass across 5 suites.

### Added — V2 Phase 7: adaptive per-user opponent (Mode F3) (`opponent_model/`, `web/`)
- A new `opponent_model/` package — a fixed strong base engine plus a small
  **per-user layer**, kept entirely separate from the evolution pipeline
  (PROJECT_GUIDE.md guardrail) so neither contaminates the other:
  - `OpponentModel` — a per-user profile keyed by position: the moves this
    player tends to make, their opening tendencies, and their *recurring
    mistakes* (positions where their move worsens their standing once the
    opponent's best 1-ply reply is included, so it catches tactical blunders,
    not just positional ones). Serialises to a plain dict for persistence.
  - `AdaptiveEngine` — the base engine (scalar **or** NN genome, untouched) with
    an exploit layer: it steers toward lines where *this* user's likely (often
    weak) reply hurts them most. Two honesty guards keep it strong — **unknown
    position ⇒ assume the user plays best** (so it falls back to the base move),
    and **never self-harm** (a deviation must stay within a safety margin of the
    base-best). How hard it leans on the exploit scales with games seen, so a
    returning player meets a sharper opponent (PRD: "harder over sessions").
- `adaptive_demo.py` — the Phase 7 acceptance check: the model watches a
  habitual user over several sessions and its per-user profile visibly fills in
  (positions known, recurring mistakes, sharpness ramping). The base engine is
  never modified. Tests in `tests/test_opponent_model.py` (10, incl. cold model
  == base engine, and a flagged recurring blunder).
- **Wired into the viewer as Mode F3**: an *Adaptive* dial in Play mode. The
  server keeps a per-user model (in-memory + one JSON file per user under
  `web/opponent_models/`, gitignored), updates it when each game ends
  (`/api/adaptive_learn`), and shows a live profile readout
  (`/api/adaptive_profile`). Reentrant model lock fixes a self-deadlock between
  the learn endpoint and the model loader.
- `supabase/schema.sql`: an `opponent_models` table (RLS, owner-scoped) as the
  production home for the per-user model — read/written server-side (the local
  viewer or the optional FastAPI backend), since the browser never runs the
  Python engine.

### Changed — NN evaluator is now a residual on the handcrafted eval (`engine/nn_eval.py`)
- `nn_evaluate` returns `handcrafted_eval + learned_correction` instead of a
  from-scratch score. A near-zero net ≈ the handcrafted eval, so the initial GA
  population already plays at ~baseline strength and evolution only refines
  upward. (From-scratch evolution couldn't beat the handcrafted eval at a
  practical scale — a 7-hour pop16/gen20 run scored 29.7%; under the residual it
  scores 50% and short runs cross 50%.)
- Cached the unpacked weight matrices on the genome — one reshape per game
  instead of per leaf node, so NN evaluation (and thus evolution) is faster.

### Added — V2 Phase 6: neural-net evaluator, now evolvable (`engine/nn_eval.py`, `ga/`)
- A small MLP evaluator: 10 raw board features → 8 hidden (tanh) → 1 output
  scaled to centipawns; the flat 97-weight vector is the genome. No backprop —
  the GA evolves the weights directly.
- The search dispatches on genome type, so an `NNGenome` drives the existing
  engine/search unchanged — an NN engine plays legal games.
- **The GA is now genome-agnostic**: crossover/mutation rebuild whichever genome
  type they're given, the tournament workers reconstruct per-side by kind, and
  `EvolutionConfig.genome_kind="nn"` evolves the network (NN champion benchmarked
  vs the hand-tuned scalar eval). `python evolve.py --nn` runs it; the scalar
  pipeline is unchanged. Tests in `tests/test_nn.py`.
- `notebooks/cloud_evolution.ipynb`: a CPU-only Google Colab notebook to run a
  big NN/GA evolution in the cloud and download the JSON artifacts. (A 97-weight
  network needs a large run to beat the handcrafted eval — that's the cloud job.)
- The play viewer auto-loads an evolved net as a **"Neural Net (evolved)"
  opponent** whenever `web/nn_weights.json` is present — the server reconstructs
  an `NNGenome` for it. Drop in a cloud-trained file to upgrade it.

### Added — Tournament of Champions + evolution analytics (`web/showcase.*`)
- `training/tournament_data.py` runs a knockout of each generation's champion
  (`ga/knockout.py`): winners advance and **absorb the loser** (winner-dominant
  crossover + mutation) into a hybrid, round after round, down to one ultimate
  champion. Records every match's move trace + every merge's lineage to
  `web/tournament.json`.
- Showcase **Tournament** tab: animated bracket (run/reveal), per-match replay
  with eval bar, merge notes, and a champion banner with the champion's genome.
- Showcase **Evolution & Analytics** tab expanded: a summary (strength gained,
  generations, champion), the strength curve, a fitness-spread chart (best /
  average / weakest per generation), and a weight-drift chart (how the
  champion's five evaluation weights evolve) — all from the run data.

### Added — Move variety in the viewer (fresh games, not one fixed line)
- Optional `random_margin` on search/`Engine`: when > 0, the root picks
  uniformly among moves within that many centipawns of the best, so repeated
  games differ without playing weak moves (forced tactics still chosen). The web
  viewer enables it for Watch AI-vs-AI (`variety` flag on `/api/engine`). The GA
  stays fully deterministic (margin 0) so fitness remains reproducible.

### Changed — Repetition draw is now a house rule (perpetual-check only)
- Repeating a position draws **only** when the repeated cycle involved checks
  (a perpetual check). Plain threefold/fivefold repetition of ordinary moves no
  longer ends the game — the engine plays on. The no-progress fifty/seventyfive-
  move rules remain as a backstop. Centralised in `engine/rules.py`
  (`is_draw`/`is_game_over`/`describe_termination` + new `game_result`) and used
  consistently by the search, engine, self-play, GA match, and the web viewer
  (which now uses these instead of python-chess's `claim_draw=True`).

### Added — Phase 5: Auth + storage (Supabase) (`web/`, `supabase/`)
- Client-side Supabase auth (email + password) and per-user game storage, with
  **Row Level Security** so each user only ever sees their own rows — no backend
  to host, no service-role key in the browser, deploys static.
- `supabase/schema.sql`: `profiles` + `games` tables, RLS policies, and an
  auto-create-profile trigger on signup. `mode` matches the engine's PGN tag.
- `web/auth.js`: lazy-loaded Supabase client + a sign up / in / out panel;
  exposes `window.DarwinCloud` (saveGame / listGames). Degrades gracefully when
  unconfigured/offline — the viewer still plays.
- Frontend: auth panel, **Save game** (builds a PGN client-side and stores it),
  and a **My games** list (click to copy PGN). `web/supabase-config.example.js`
  template; real `web/supabase-config.js` is gitignored.
- Honours PROJECT_GUIDE.md: single database (Supabase), secrets never committed, anon
  key client-side / service-role key never shipped.

### Added — Phase 4: Play vs Trained AI (`web/` + `training/make_opponents.py`)
- The play viewer now faces the **evolved** engine, not the hand-tuned default.
  `make_opponents.py` turns a GA run into `web/opponents.json` — a difficulty
  ladder from a Generation-0 "hatchling" up to the deep-thinking champion,
  ramping on two honest axes (weaker→stronger evolved genome, shallow→deep
  search).
- Server loads the ladder and resolves a chosen opponent id to its genome +
  depth (`_engine_for`, `/api/opponents`); falls back to a default-genome ladder
  if no run exists yet, so play still works untrained.
- Frontend gains an **Opponent** dial (with a blurb) shown in Play mode; Watch
  mode keeps the raw depth selector. The human's moves are answered by the
  selected trained opponent.

### Added — Phase 3: Evolution showcase (`web/showcase.*`)
- A fully static, data-driven showcase that replays a GA run in the browser with
  **no engine in the loop** (reads only `showcase.json`), so it deploys to a
  static host unchanged — honouring "heavy compute offline, frontend reads
  artifacts".
- **Colosseum** — every game of a generation's tournament replayed at once on a
  grid of mini-boards, position-by-position, with result badges; click any board
  to **feature** it large with a live **eval bar** and a move clock (the
  PROJECT_GUIDE.md "two versions + eval bar + clocks" core).
- **Genomes Bonding** — an animation of two parent genomes crossing over into a
  child: each gene visibly inherited from one parent (colour), mutations sparked
  (gold), driven by the GA's real `crossover_mask` + `mutations` lineage.
- **Evolution Curve** — the per-generation strength (win-rate vs baseline) as a
  clickable line chart, plus the champion genome vs the hand-tuned baseline.
- `training/showcase_data.py` generates `web/showcase.json`; the GA gained an
  opt-in per-game FEN/eval move trace (`log_moves`) to feed it. Server serves the
  new static routes (`/showcase`, `showcase.{css,js,json}`).

### Added — Phase 2: Genetic algorithm (`training/ga/`)
- Neuroevolution of the evaluation `Genome` (scalar feature weights) via
  self-play: `ga/` package with genetic operators (`genome_ops.py`: random
  init, uniform crossover, Gaussian mutation), single-game play with objective
  material adjudication (`match.py`), parallel double round-robin + baseline
  benchmark (`tournament.py`), and the evolution loop with elitism and
  tournament selection (`evolution.py`).
- Strength curve as the Phase 2 acceptance check: each generation's best genome
  is benchmarked against the fixed hand-tuned `DEFAULT_GENOME` from a fixed
  opening set; `evolve.py` prints the curve and saves the strongest genome to
  `weights.json`. Verified the curve rises and the evolved genome beats the
  baseline (~58% → ~67%).
- Lineage + game logging baked in (`lineage.py`, written as `run.json` +
  `strength.csv`): every crossover records its two parents, per-gene crossover
  mask, and mutations; every tournament game records its result/termination —
  the data contract for the Phase 3 "colosseum" grid and "genomes bonding"
  animation (real data, not faked).
- Tests for operators, point-conservation in round-robin, benchmarking, and a
  full tiny evolution run with lineage assertions (`tests/test_ga.py`).

### Added — Phase 1: Engine MVP (`training/`)
- Minimax search with alpha-beta pruning, iterative deepening, capture-first
  move ordering, and depth-adjusted mate scores (`engine/search.py`).
- Handcrafted evaluation as a weighted sum of features — material,
  piece-square tables, mobility, king safety, pawn structure — with the weight
  vector exposed as an evolvable `Genome` for the Phase 2 GA
  (`engine/evaluation.py`).
- `Engine` wrapper API: `select_move`, `analyse`, `eval_bar_score`
  (`engine/engine.py`).
- PGN export for recorded games (`chess_io/pgn.py`).
- `selfplay.py` (engine-vs-engine demo / acceptance check) and `play.py`
  (human-vs-engine terminal CLI).
- Centralised draw rules in `engine/rules.py`: threefold-repetition and
  perpetual-check detection, plus `is_draw` / `is_game_over` /
  `describe_termination` helpers, reused by the search, self-play, and viewer.
- Search treats threefold repetition (including perpetual check) as a draw, so
  the engine seeks a saving perpetual when losing and avoids throwing a win away
  into one.
- Test suite covering move legality, mate-in-one, capturing hanging material,
  threefold/perpetual-check draw detection, evaluation symmetry, and genome
  serialisation (`tests/test_engine.py`).
- `training/requirements.txt` and `training/README.md`.

### Added — Local board viewer (`web/`)
- Visual, playable chessboard backed by the real engine via a stdlib-only local
  server (`web/server.py`): JSON API for legal moves, human moves, and engine
  replies, with python-chess as the single source of rules.
- Two modes — **Play vs Engine** (click-to-move, legal-move highlights,
  promotion picker, choose colour/depth) and **Watch AI vs AI** — plus a live
  eval bar, move list, and game status (`web/index.html`, `style.css`, `app.js`).
- Unicode-glyph pieces so the viewer runs fully offline (no CDN, no build step).

### Fixed
- Search now restores the board exactly when a per-move time budget expires
  mid-line (previously a timeout left moves on the stack and could surface as an
  "illegal move").

### Planned
- (V2) A large cloud NN-evolution run to actually beat the handcrafted eval, then
  wire the evolved NN into the play viewer as an opponent.
- (V2) Adaptive per-user opponent model (Phase 7).
- (V2) Continual experience-pool training pipeline.

## [0.1.0] — 2026-06-20
### Added
- Initial project scaffold and documentation set.
- `README.md`, `PROJECT_GUIDE.md`, and `docs (PRD, TRD, GSD, UIUX).
- `.gitignore` and `.env.example` for Supabase configuration.
- Defined architecture: offline Python training → light Vercel frontend; Supabase for auth/data.
- Defined scope and honest constraints (self-improving, not superhuman).
