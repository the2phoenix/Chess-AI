# Deploying Darwin's Gambit

A step-by-step guide for putting the project online. **Nothing here is destructive
or automatic — do it when you're ready** (after the Colab training push is a good
time, so you deploy a strong engine).

---

## How it splits (read this first)

The app has two halves, and they host in two different places:

| Part | What it is | Where it goes | Why |
|---|---|---|---|
| **Frontend** | The board UI + the static **Showcase** (reads `showcase.json` / `tournament.json`) | **Vercel** | Static files, global CDN, free |
| **Engine API** | `web/server.py` — computes legal moves, engine replies, the adaptive opponent | **Render** | Runs Python; Vercel can't run a live Python engine |

The Showcase works on **Vercel alone**. Live *play / watch / adaptive* needs the
**Render** backend, which the frontend calls via `window.DARWIN_API_BASE`.

> Heavy compute (evolution) is **never** hosted — it runs offline on Colab. Render
> only does fast per-move search, so the free tier is fine for casual play.

---

## Part A — Push to GitHub

You create an empty repo on github.com (no README/.gitignore — the repo already
has them). Then, from `D:\chessai`:

```bash
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

(The repo is already committed locally, secrets are gitignored, and large run
dumps are excluded.)

---

## Part B — Deploy the Engine API on Render

1. Go to <https://render.com> → sign up (free) → **New ▸ Blueprint**.
2. Connect your GitHub and pick this repo. Render reads **`render.yaml`** and
   proposes a service `darwins-gambit-api` (Python, free plan).
3. Click **Apply**. First build takes a few minutes (installs `chess` + `numpy`).
4. When live, copy the URL, e.g. `https://darwins-gambit-api.onrender.com`.
5. Test it: open `https://darwins-gambit-api.onrender.com/` — you should see the
   viewer (the backend can serve the page too). Or hit the API directly.

What `render.yaml` sets: `startCommand: python web/server.py`; the server reads
Render's `PORT`, binds `0.0.0.0`, and sends CORS headers. Pin `DARWIN_CORS_ORIGIN`
to your Vercel URL (Part D) once you have it.

---

## Part C — Deploy the Frontend on Vercel

1. Go to <https://vercel.com> → **Add New ▸ Project** → import this repo.
2. **Set the Root Directory to `web`** (Settings ▸ General ▸ Root Directory). This
   is important — the site lives in `web/`, and `web/vercel.json` handles the
   `/showcase` route.
3. Framework preset: **Other** (no build step — it's static). Leave build/install
   commands empty.
4. Deploy. You'll get a URL like `https://darwins-gambit.vercel.app`.

At this point the **Showcase** (`/showcase`) already works. Live play won't yet —
it's still pointed at "same origin," which on Vercel has no engine. Fix that next.

---

## Part D — Wire the two together

1. **Point the frontend at the backend.** Edit `web/app-config.js`:
   ```js
   window.DARWIN_API_BASE = "https://darwins-gambit-api.onrender.com";
   ```
   Commit + push → Vercel redeploys automatically. Now the board calls Render.

2. **Lock the backend's CORS** to your site. In Render ▸ your service ▸ Environment,
   set `DARWIN_CORS_ORIGIN` to `https://darwins-gambit.vercel.app` and save (it
   redeploys). Now only your site can call the API.

3. **Supabase (auth) on the live site.** `web/supabase-config.js` is gitignored
   (so it never lands in git), so it won't be on Vercel by default — the site
   still runs, just without sign-in. To enable auth in production:
   - The **anon/publishable key is browser-safe**, so it's fine to commit a
     production `web/supabase-config.js` (copy from `supabase-config.example.js`),
     **or** add the two values as a committed file just for deploy.
   - In Supabase ▸ Authentication ▸ URL Configuration, add your Vercel URL to
     **Site URL** and **Redirect URLs**, and add the Vercel origin to Google
     OAuth's authorized origins/redirects (same fix as the local `redirect_uri`
     one). The **service-role key is never used in the browser** — don't add it.

---

## Updating after Colab training

When a Colab run gives you a stronger `nn_weights.json`:
1. Drop it into `web/nn_weights.json`, commit, push.
2. Vercel redeploys the frontend; **redeploy the Render service** (Manual Deploy ▸
   Deploy latest commit) so the engine backend loads the new net.

The same goes for refreshed `showcase.json` / `tournament.json` / `opponents.json`
(regenerate with `training/showcase_data.py`, `tournament_data.py`,
`make_opponents.py`), then commit + push.

---

## Caveats (free tier, honest)

- **Cold starts:** Render's free instance sleeps after ~15 min idle; the first
  move after a nap takes ~30–60 s while it wakes. Fine for a demo/portfolio.
- **Ephemeral disk:** the adaptive per-user models (`web/opponent_models/`) and
  the experience pool (`training/pool/`) written on Render reset on each redeploy.
  For durable per-user models, move them to the Supabase `opponent_models` table
  (the schema is already there) — a later enhancement.
- **The Showcase needs no backend** — if you only deploy Vercel, the evolution
  story (Colosseum, Tournament, Bonding, Analytics) is fully live; just the
  "play a live game vs the engine" buttons need Render.
- **Don't deploy the evolution/pipeline to a serverless function** — it will time
  out. That stays on Colab. (This is the PROJECT_GUIDE.md guardrail.)
