# web/ — Darwin's Gambit board viewer

A visual, playable chessboard for the engine. **Run it locally** to play the
evolved AI, watch it play itself, face the adaptive opponent, or open the
evolution Showcase.

> This is a **local development viewer**, not the production deployment. It runs
> a small Python server that calls the real engine in `../training` (python-chess
> owns the rules; the engine supplies its moves). The eventual Vercel frontend
> will instead read static artifacts (`weights.json` / PGN) and never run heavy
> compute in a serverless function — per the project's architecture.

## Run

```bash
cd web
python server.py            # opens http://localhost:8000 automatically
```

Options: `python server.py --port 8080 --no-browser`.

The server needs the engine deps installed (`pip install -r ../training/requirements.txt`).

## What you can do

- **Play vs Trained AI** — pick your colour and an opponent from the difficulty
  ladder, then click a piece and a destination. Legal moves are highlighted; pawn
  promotions pop a picker.
- **Adaptive (Mode F3)** — flip the Adaptive dial on: a fixed-strong base engine
  that learns and exploits *your* habits, with a live profile readout that
  sharpens the more you play.
- **Watch AI vs AI** — the engine plays both sides (a fresh game each time); press
  ▶ Start / ⏸ Pause.
- **Showcase** (`/showcase`) — Colosseum, Tournament of Champions, Genomes
  Bonding, and Evolution & Analytics, all from static JSON (no engine needed).
- **Eval bar** (left) shows the engine's evaluation from White's perspective; the
  move list and game status update live.

## How it works

- `server.py` — stdlib HTTP server (no framework). Serves the page and a tiny
  JSON API: `/api/new`, `/api/legal`, `/api/move`, `/api/engine`, the adaptive
  endpoints (`/api/adaptive_move` via `/api/engine`, `/api/adaptive_learn`,
  `/api/adaptive_profile`), and `/api/pool_add`. Stateless — the full **move
  history** travels with each request, so draw-by-repetition detection works.
- `index.html` / `style.css` / `app.js` — the board UI. Pieces are Unicode
  glyphs (no image downloads), so it works fully offline. `showcase.*` is the
  static evolution showcase.
- It reads `window.DARWIN_API_BASE` (`app-config.js`): empty for local, or a
  hosted engine URL in production.

No build step, no npm, no external CDN.
