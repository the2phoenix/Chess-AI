# Technical Requirements Document — Darwin's Gambit

## 1. Architecture overview

Two decoupled halves joined by data files:

```
[ OFFLINE: training/  ]            [ ONLINE: web/ on Vercel ]
 Python engine + GA      --->       JS frontend
 self-play tournaments   weights.json   - board UI (custom, Unicode pieces)
 (heavy, one-time/        + games.pgn    - play modes
  periodic, on cloud)    ------------>    - Supabase auth + data
                                          |
                                   (optional) Python engine API on Render
                                          for live server-side play
```

**Principle:** all heavy compute is offline and produces small artifacts (`weights.json`, recorded PGN). The deployed app only *reads* them, so it stays light on any device.

## 2. Stack decisions

| Concern | Choice | Why |
|---|---|---|
| Engine language | Python | python-chess (rules), NumPy, easy analysis, Colab-friendly |
| Chess rules | python-chess | Don't reinvent move generation; focus on the AI |
| NN framework | NumPy | Tiny MLP forward pass only; the GA evolves the weights (no backprop, no GPU) |
| Parallelism | multiprocessing | Tournament games are independent → spread across CPU cores |
| Training compute | Google Colab (CPU) | Free, off the laptop; CPU-parallel, no GPU needed |
| Frontend | HTML/CSS/JS (custom board, Unicode pieces) | No framework, no build step; runs in any browser |
| Hosting | Vercel (Hobby) | Free static/edge hosting; perfect for a light frontend |
| Auth + DB | **Supabase** | Postgres fits relational chess data + built-in auth (email + Google OAuth) |
| Live backend (opt) | Python engine API on Render | Long-running search (Vercel functions can't) |

### Auth + storage
Supabase handles **both** auth and storage: email + password and Google OAuth for
login, Postgres for data, and Row-Level Security so each user only ever sees their
own rows. One database, one provider — no second data store. The schema is in
`supabase/schema.sql`.

## 3. Performance constraints (honest)

- **Vercel Hobby functions are short-lived (~10–60s) with a small monthly CPU budget** — they cannot run evolution or live tournaments. Heavy compute stays offline.
- **Python minimax is slower than JS** — mitigate with shallow search (depth 2–3) during evolution, multiprocessing, and PyPy if needed.
- **Evolving NN weights converges slowly** — keep the network small; the bottleneck is CPU game-play (there is no gradient/GPU step at all), so the residual design starts the net at baseline strength.
- **Browser showcase** should *replay recorded games* or run shallow/fast matches — never 30 heavy live games at once.

## 4. Data model

**Supabase / Postgres** (see `supabase/schema.sql`), all owner-scoped by RLS:

```sql
-- users handled by Supabase Auth (auth.users)

profiles         (id uuid pk -> auth.users, username, created_at)
games            (id, user_id, white, black, result, termination, plies,
                  pgn, mode, created_at)     -- mode: ai_vs_ai | vs_trained | vs_adaptive
opponent_models  (user_id pk, model jsonb, games_seen int, updated_at)
```

**Offline training artifacts** (local files, not Postgres — managed by the Python
pipeline, read by the frontend as static JSON):

- `weights.json` / `nn_weights.json` — evolved genomes.
- `deployed/registry.json` — the versioned champion registry (each promoted
  engine + its benchmark), the local equivalent of an `engine_versions` table.
- `pool/` — the experience pool (per-game JSON + PGN), `source: self_play | human`,
  that feeds the offline retraining loop.
- `showcase.json` / `tournament.json` — replay + analytics data for the Showcase.

## 5. Security requirements

- **No secrets in the repo.** Supabase keys go in env vars only (`.env`, never committed). See `.env.example`.
- Use Supabase **Row Level Security**: a user can read/write only their own `profiles`, `games`, `opponent_models`.
- The Supabase **anon key** is safe client-side *only with RLS enabled*; the **service-role key** is server-side only — never ship it to the browser.

## 6. Integration points

- **Frontend → Supabase:** auth (email / Google OAuth), read/write games + profile.
- **Frontend → static artifacts:** fetch `weights.json` / `nn_weights.json` /
  `showcase.json` / PGN from the deployed bundle.
- **Offline trainer → artifacts:** the pipeline writes the deployed registry and
  the experience pool as local JSON, and the evolved weights the frontend reads.
- **Frontend → Python engine API (`web/server.py`):** POST a position, receive the
  engine's move for live play (locally in dev, or a hosted instance in production).

## 7. Build order

Follow `PROJECT_GUIDE.md` build phases. MVP first: engine → GA over scalar weights → AI-vs-AI showcase → vs-trained mode → auth. Only then: NN evaluator, adaptive model, continual pipeline.
