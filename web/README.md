# web/ — Darwin's Gambit board viewer

A visual, playable chessboard for the Phase 1 engine. **Run it locally** to see
the pieces, watch the engine play itself, or play against it by clicking.

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

- **Play vs Engine** — pick your colour and engine depth, then click a piece and
  click a destination. Legal moves are highlighted; pawn promotions pop a picker.
- **Watch AI vs AI** — the engine plays both sides; press ▶ Start / ⏸ Pause.
- **Eval bar** (left) shows the engine's evaluation from White's perspective; the
  move list and game status update live.

## How it works

- `server.py` — stdlib HTTP server. Serves the page and exposes a tiny JSON API:
  `/api/new`, `/api/legal` (legal targets for a square), `/api/move` (apply a
  human move), `/api/engine` (engine's reply). Stateless — the board FEN travels
  with each request.
- `index.html` / `style.css` / `app.js` — the board UI. Pieces are Unicode
  glyphs (no image downloads), so it works fully offline.

No build step, no npm, no external CDN.
