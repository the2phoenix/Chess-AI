# General System Design — Darwin's Gambit

*The system-design document: how the pieces actually work. Pairs with the TRD
(stack/requirements).*

## 1. The chess engine

Two parts: **search** (fixed) and **evaluation** (evolved).

### Search — Minimax + Alpha-Beta
- Looks ahead N plies, assuming both sides play their best.
- Alpha-beta pruning skips branches that can't change the result, enabling deeper
  search at the same cost.
- **Iterative deepening** (timed mode): search depth 1, 2, 3… keeping the best
  move found, until a time budget runs out.
- Depth 2–3 during evolution (fast); deeper for showcase/play.

### Evaluation — the evolved part
Scores a leaf position. Two versions:

**MVP — handcrafted, evolved weights.** A weighted sum of features:
`score = w1·material + w2·piece_square + w3·mobility + w4·king_safety + w5·pawn_structure`
The **genome** = the weight vector `[w1…w5]`.

**V2 — neural-network evaluator, evolved weights.** A small multilayer perceptron
in place of the formula:
- Input: **10 hand-crafted features** (material differences per piece type,
  piece-square score, mobility, king safety, pawn structure, side to move) — not
  raw board planes, which keeps the network tiny and fast.
- Network: 10 inputs → 8 hidden (tanh) → 1 output = **97 weights**, implemented in
  NumPy (the forward pass only — no PyTorch, no backprop).
- **Residual design:** the network output is a *correction* added to the
  handcrafted evaluation, so a near-zero net ≈ the handcrafted eval. Evolution
  starts at baseline strength and only has to find improvements.
- The **genome** = all 97 network weights. Minimax calls the NN instead of the
  formula (it dispatches on genome type).

## 2. The genetic algorithm (self-play evolution)

```
1. POPULATE   a population of engines, each with a random eval genome
2. TOURNAMENT  they play each other (shallow search, fast, parallel);
               fitness = points (win 1 / draw ½ / loss 0)
3. SELECT      tournament selection of parents by fitness
4. ELITISM     copy the top genomes unchanged into the next generation
5. BREED       uniform crossover of two parents + small Gaussian mutations
6. REPEAT      next generation plays → improves over time
```

**Anti-noise:** play each pairing twice with alternating colours; cap games
(adjudicate by material on the move limit) so they can't run forever.
**Progress metric:** each generation, benchmark the champion vs a fixed baseline
engine from a set of openings and log the win rate → the strength curve.

The same operators evolve **either** genome type — the 5-weight scalar `Genome`
or the 97-weight `NNGenome` — because crossover/mutation rebuild whichever type
they're handed.

## 3. Continual-learning pipeline (V2)

One growing **experience pool** (on disk: per-game JSON + PGN) fed two ways:

- **Self-play** (the `collect` step): engines grind games → pool.
- **Human play** (Mode F3): the viewer posts finished games → the same pool.

Loop (`training/pipeline.py`): `collect games → evolve on the pool (warm-started
from the current champion, openings sampled from the pool) → promote the
candidate only if it beats the incumbent by a margin → repeat`.
**Honest:** improvement is *periodic and offline*, not instant after one game. The
deployed champion is versioned in a local registry and only ever gets stronger.

## 4. Adaptive opponent model (Mode F3)

A **fixed strong base engine** + a **per-user layer** (`training/opponent_model/`):
- Log the user's games → build a profile: opening tendencies and recurring
  mistake positions (a move flagged when it worsens their own standing after the
  opponent's best 1-ply reply).
- Bias the engine's move choice toward lines that exploit this user's habits,
  with two guards: unknown position ⇒ assume the user plays best (fall back to the
  base move), and never deviate far enough below the base-best to self-harm.
- Persist per-user (`opponent_models`); sharpen as games seen grows.
- **The base engine is never fine-tuned on user games** (that risks catastrophic
  forgetting) — all personalization lives in the separate per-user layer.
- **Kept separate** from the evolution experiment so neither contaminates the other.

## 5. Mode flows

**AI vs AI (F1):** two engine genomes alternate minimax moves → render board, eval
bar (engine's own score), move list → record PGN. Move variety keeps each game fresh.

**Vs Trained (F2):** load a chosen rung of the difficulty ladder → user moves via
the board UI → engine replies → repeatable, no learning.

**Vs Adaptive (F3):** load the base engine + the user's opponent model → user plays
→ engine plays well and exploits the user → after the game, update the user's model.

## 6. Offline → online handoff

The offline trainer (Python, on Colab or a laptop) produces small artifacts:
`weights.json` / `nn_weights.json` (evolved genomes), `showcase.json` /
`tournament.json` (replay data), and PGN. The frontend reads those directly — the
static Showcase needs no engine at all.

For **live play**, the NN evaluator runs as plain NumPy inside the Python engine
(`web/server.py`) — there is no in-browser model and no TensorFlow.js/ONNX export.
The static frontend calls that engine API for moves (locally during development,
or a hosted instance in production).

## 7. Honest ceiling

Strength is bounded by compute and population/generation budget — this is a system
that *clearly improves and self-teaches*, not a superhuman one. Everything is
designed, measured, and reported around "gets stronger the more it plays."
