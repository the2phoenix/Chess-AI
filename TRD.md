# Technical Requirements Document — Darwin's Gambit

## 1. Architecture overview

Two decoupled halves joined by data files:

```
[ OFFLINE: training/  ]            [ ONLINE: web/ on Vercel ]
 Python engine + GA      --->       JS frontend
 self-play tournaments   weights.json   - board UI (chess.js + chessboard.js)
 (heavy, one-time/        + games.pgn    - play modes
  periodic, on cloud)    ------------>    - Supabase auth + data
                                          |
                                   (optional) FastAPI backend on Render
                                          for live server-side play
```

**Principle:** all heavy compute is offline and produces small artifacts (`weights.json`, recorded PGN). The deployed app only *reads* them, so it stays light on any device.

## 2. Stack decisions

| Concern | Choice | Why |
|---|---|---|
| Engine language | Python | python-chess (rules), NumPy, easy analysis, Colab-friendly |
| Chess rules | python-chess | Don't reinvent move generation; focus on the AI |
| NN framework | PyTorch | For the evolved neural-net evaluator (V2) |
| Parallelism | multiprocessing | Tournament games are independent → spread across cores |
| Training compute | Google Colab / Codespaces | Free, off the laptop, GPU available if needed |
| Frontend | HTML/CSS/JS + chess.js + chessboard.js | Runs in any browser; light |
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
- **Evolving NN weights converges slowly** — keep the network small; the bottleneck is CPU game-play, so a GPU helps less than for gradient training.
- **Browser showcase** should *replay recorded games* or run shallow/fast matches — never 30 heavy live games at once.

## 4. Data model (Supabase / Postgres)

```sql
-- users handled by Supabase Auth (auth.users)

profiles            (id uuid pk -> auth.users, username, created_at, elo_estimate)
games               (id, white_player, black_player, pgn, result,
                     mode, created_at)          -- mode: ai_vs_ai | vs_trained | vs_adaptive
opponent_models     (id, user_id fk, model_json jsonb, games_seen int, updated_at)
engine_versions     (id, generation int, weights_json jsonb, strength_score,
                     created_at)                 -- evolved engines, for showcase + play
experience_pool     (id, pgn, source, created_at)  -- source: self_play | human
```

- Per-user adaptation (opponent model) lives in `opponent_models`, keyed by user, so it persists across sessions/devices.
- `engine_versions` stores each generation's weights so the showcase can pit Gen-X vs Gen-Y.
- `experience_pool` feeds the offline retraining loop.

## 5. Security requirements

- **No secrets in the repo.** Supabase keys go in env vars only (`.env`, never committed). See `.env.example`.
- Use Supabase **Row Level Security**: a user can read/write only their own `profiles`, `games`, `opponent_models`.
- The Supabase **anon key** is safe client-side *only with RLS enabled*; the **service-role key** is server-side only — never ship it to the browser.

## 6. Integration points

- **Frontend → Supabase:** auth (email/OAuth), read/write games + profile + opponent model.
- **Frontend → static artifacts:** fetch `weights.json` / PGN from the deployed bundle or Supabase storage.
- **Offline trainer → Supabase:** writes new `engine_versions` and reads `experience_pool` (via service-role key, server-side).
- **(Optional) Frontend → FastAPI backend:** POST a position, receive the engine's move for live play.

## 7. Build order

Follow `PROJECT_GUIDE.md` build phases. MVP first: engine → GA over scalar weights → AI-vs-AI showcase → vs-trained mode → auth. Only then: NN evaluator, adaptive model, continual pipeline.
