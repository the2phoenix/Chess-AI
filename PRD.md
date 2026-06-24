# Product Requirements Document — Darwin's Gambit

## 1. Vision

A chess platform where the AI opponent was never taught chess strategy — it teaches itself by playing millions of games against itself, evolving from random play to genuine competence. Users can watch this self-taught intelligence battle itself, test themselves against it, or face an opponent that learns *their* style over time.

## 2. Problem / motivation

Most chess engines are either hand-programmed with human strategy or trained on massive human game databases. This project demonstrates a different, more elegant idea: **intelligence emerging from self-play and selection alone**, with no human knowledge baked in. It's a showcase of evolutionary AI that's both technically rigorous and genuinely fun to watch.

## 3. Target users

- **Examiners / faculty** — evaluating a technically serious, original AI project.
- **Casual players** — want a fun, adaptive chess opponent.
- **The curious** — want to *watch* an AI teach itself, not just play it.

## 4. Core features

### F1 — AI vs AI showcase
Two evolved engines play, with a live evaluation bar, move list, and chess clocks. Users can select which generations face off. **Headline demo: Gen-1 vs Gen-N**, visibly proving the AI improved.

### F2 — Play vs Trained AI
User plays the fixed, fully-evolved champion. Difficulty dial via generation selection or search depth/time. No learning — a pure, repeatable challenge.

### F3 — Play vs Adaptive AI
A strong pre-trained base that *also* personalizes to the user: it logs their games, models their patterns and recurring mistakes, and gets harder over repeated sessions. Plays well immediately (thanks to the base) and sharpens against the specific user over time.

### F4 — Accounts & persistence
Sign up / log in (Supabase Auth). Store user profile, game history, per-user opponent model, and stats so the adaptive AI remembers them across sessions and devices.

### F5 — Self-improvement pipeline (offline)
A continual-learning loop: games (from self-play and human play) accumulate into an experience pool; periodic offline evolution improves the engines; stronger engines are redeployed.

## 5. User stories

- *As a visitor*, I can watch two AIs play a full game without signing in.
- *As a player*, I can log in and play the trained AI at a chosen difficulty.
- *As a returning player*, I find the adaptive AI noticeably tougher because it remembers how I play.
- *As an examiner*, I can see a strength-over-generations chart proving the AI learned.

## 6. Scope

**MVP (must ship):**
- Working chess engine (minimax + alpha-beta + handcrafted evaluation).
- Genetic algorithm evolving evaluation weights; demonstrable improvement over generations.
- AI vs AI showcase with eval bar (F1).
- Play vs Trained AI (F2).
- Basic auth + game storage (F4, minimal).

**V2 (level-up):**
- Neural-network evaluator evolved by the GA (replaces handcrafted eval).
- Adaptive opponent model (F3).
- Continual experience-pool pipeline (F5).

**Later / optional:**
- Live server-side play via FastAPI backend.
- Leaderboards, ELO estimation, shareable game replays.

## 7. Success metrics

- A later-generation engine beats an earlier-generation one in >80% of games.
- Visible rising strength curve (win rate vs a fixed baseline) across generations.
- Adaptive AI's win rate against a repeat human improves across sessions.
- A clean, deployable demo that runs without straining the presenter's laptop.

## 8. Non-goals (explicitly out of scope)

- **Superhuman / "unbeatable" strength.** Not achievable on available compute; not the goal.
- **Training on human game databases or opening books.** The point is learning from scratch.
- **Real-time multiplayer between humans.**
- **Mobile-native apps** (responsive web only).
