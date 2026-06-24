# Project Guide — Context & Rules

> Project context, architecture, build order, and the guardrails the codebase
> follows. Companion docs: `PRD.md` (product), `GSD.md` (system design),
> `TRD.md` (stack/data model).

## What this project is

**Darwin's Gambit** — a chess engine that teaches itself to play via
neuroevolution (a genetic algorithm evolving an evaluation function through
self-play). Three modes: AI-vs-AI showcase, play-vs-trained-AI,
play-vs-adaptive-AI. See `PRD.md` for product, `GSD.md` for system design,
`TRD.md` for the stack.

## Stack

- **Engine + training (offline, Python):** python-chess, NumPy, multiprocessing.
  Runs on Colab/Codespaces.
- **Frontend:** HTML/CSS/JS (no build step); deploys static to Vercel.
- **Auth + data:** Supabase (Postgres + Auth) — primary. **One database only.**
- **Optional backend:** the Python engine API on Render (for live play).

## Repo layout

```
/training   Python engine, GA, NN, opponent model, pipeline   (offline, heavy)
/web        Frontend + local viewer + Supabase integration     (light)
/supabase   Database schema + RLS policies
/notebooks  Colab training notebooks
PRD.md TRD.md GSD.md UIUX.md   product & system docs
```

## Build order — done in phases, each verified before the next

1. **Engine MVP** — minimax + alpha-beta + a handcrafted evaluation function;
   plays legal, sensible chess (python-chess for rules).
2. **GA over scalar weights** — evolve the evaluation weights via self-play
   tournaments; the strength curve rises over generations.
3. **AI-vs-AI showcase** — frontend that replays/plays two engine versions with
   eval bar + clocks.
4. **Play vs Trained AI** — human input -> engine reply; difficulty dial.
5. **Auth + storage** — Supabase login, store games/profile.
6. **(V2) NN evaluator** — a small evolved neural net in place of the handcrafted
   eval, search kept shallow.
7. **(V2) Adaptive opponent model** — per-user pattern learning (Mode F3).
8. **(V2) Continual experience-pool pipeline.**

The MVP (phases 1-5) shipped and was verified before the V2 work.

## Hard rules / guardrails

- **Heavy compute is offline only.** Evolution and live tournaments never run in
  a serverless function (they time out). The frontend only reads `weights.json`
  / `nn_weights.json` / PGN.
- **Secrets:** never read, print, hardcode, or commit API keys. Use env vars;
  keep `.env` gitignored. `.env.example` holds placeholders only.
- **No human chess data / opening books.** The engine learns from self-play only
  — that's the project's whole identity.
- **Honesty in framing:** this is a *self-improving* engine, not a
  superhuman/unbeatable one. Copy, comments, and report text say so.
- **Keep experiments separate:** the evolution pipeline and the per-user
  adaptation are distinct subsystems — neither contaminates the other's results.
- **Performance:** shallow search (depth 2-3) during evolution; multiprocessing
  for tournaments; the NN stays small.
- **Supabase RLS:** users access only their own rows. The service-role key is
  server-side only, never shipped to the browser.

## Conventions

- Data interchange: JSON for weights, PGN for games — language-agnostic so
  Python writes and JS reads.
- Keep `engine/`, `ga/`, `chess_io/`, `opponent_model/` as clean, reusable
  modules.
- Update `CHANGELOG.md` with each meaningful change.

## Design principle

Prefer the simplest version that ships. A feature that risks blowing the
one-month / laptop / free-tier budget gets flagged rather than half-built.
