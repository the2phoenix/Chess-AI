# General System Design — Darwin's Gambit

*Interpreting GSD as the system-design document: how the pieces actually work. Pairs with TRD (which covers stack/requirements).*

## 1. The chess engine

Two parts: **search** (fixed) and **evaluation** (evolved).

### Search — Minimax + Alpha-Beta
- Looks ahead N plies, assuming both sides play their best.
- Alpha-beta pruning skips branches that can't change the result, enabling deeper search at the same cost.
- **Iterative deepening** (showcase mode): search depth 1, 2, 3… keeping the best move found, until the time budget runs out. Enables real clock play.
- Depth 2–3 during evolution (fast); deeper for showcase/play.

### Evaluation — the evolved part
Scores a leaf position. Two versions:

**MVP — handcrafted, evolved weights.** A weighted sum of features:
`score = w1·material + w2·center + w3·king_safety + w4·mobility + w5·pawn_structure + …`
The **genome** = the weight vector `[w1…wn]`.

**V2 — neural-network evaluator, evolved weights.** A small NN replaces the formula:
- Input: board encoded as ~12 binary 8×8 planes (piece type × color) + side-to-move + castling ≈ 768+ inputs. *(Easier starter: feed hand-features instead of raw planes — far fewer inputs, faster convergence.)*
- Network: inputs → 1–2 small hidden layers (ReLU/tanh) → 1 output (position score).
- The **genome** = all network weights. Minimax calls the NN instead of the formula.

## 2. The genetic algorithm (self-play evolution)

```
1. POPULATE   ~30–100 engines, each with random eval genomes
2. TOURNAMENT  they play each other (shallow search, fast);
               fitness = points (win 1 / draw ½ / loss 0), squared
3. SELECT      pick top performers (roulette or top-N)
4. ELITISM     copy the single best genome unchanged
5. BREED       crossover two parents' genomes + small mutations
6. REPEAT      next generation plays → improves over time
```

**Anti-noise:** play each pairing several times with alternating colors; cap games (resign/draw on threefold, 50-move, or move limit) so they can't run forever.
**Progress metric:** each generation, play the champion vs a fixed baseline engine and log win rate → the strength curve.

## 3. Continual-learning pipeline (V2)

One growing **experience pool** fed two ways:

- **Self-play** (Mode F1/F5): engines grind games → pool.
- **Human play** (Mode F3): users' games → pool.

Loop: `collect games → periodically evolve/train on the pool → deploy stronger engines → repeat`.
**Honest:** improvement is *periodic and offline*, not instant after one game. One game is too noisy to learn from live.

## 4. Adaptive opponent model (Mode F3)

A **fixed strong base engine** + a **per-user layer**:
- Log the user's games → build a profile: opening tendencies, responses to threats, recurring blunder positions.
- Bias the engine's move choice toward lines that exploit this user's habits (instead of assuming optimal play).
- Persist per-user in `opponent_models`; sharpen over sessions.
- **Recommended:** opponent-modeling layer (base net untouched). **Risky alt:** fine-tuning the net on user games → catastrophic forgetting; only do gently/offline if at all.
- **Keep separate** from the evolution experiment so results stay clean.

## 5. Mode flows

**AI vs AI (F1):** load two `engine_versions` → alternate minimax moves → render board, eval bar (engine's own score), clocks, move list → record PGN → store.

**Vs Trained (F2):** load chosen generation's engine → user moves via board UI → engine replies → repeatable, no learning.

**Vs Adaptive (F3):** load base engine + user's opponent model → user plays → engine plays well + exploits user → after game, update the user's model.

## 6. Offline → online handoff

Trainer (Python, cloud) writes `engine_versions` (weights) + recorded PGN to Supabase / the bundle. Frontend (Vercel) reads them. For V2 NN inference in-browser, export the small net to TensorFlow.js or ONNX Runtime Web; otherwise run inference on the optional FastAPI backend.

## 7. Honest ceiling

Strength is bounded by compute and population/generation budget — expect a system that *clearly improves and self-teaches*, not a superhuman one. Design, measure, and report around "gets stronger the more it plays."
