# UI/UX Design — Darwin's Gambit

## 1. Design principles

- **The board is the hero.** Everything else is supporting cast — never crowd it.
- **Make the learning visible.** The whole point is "it taught itself," so the eval bar, generation labels, and strength curve are first-class UI, not afterthoughts.
- **Calm, focused, a little cinematic.** Engine chess is cerebral; the UI should feel composed, not noisy.
- **Readable at a glance.** Whose turn, who's winning, how much time left — instantly clear.

## 2. Visual direction

- **Mood:** dark, modern, "lab meets chessboard." Deep near-black background, one cool accent (electric blue or teal) for highlights and the eval bar.
- **Board:** clean, high-contrast squares; subtle highlight for last move and legal moves; smooth piece transitions.
- **Typography:** one clean sans for UI (e.g., Inter); a mono for clocks, eval scores, and move list (numbers should line up).
- **Restraint:** limited palette, generous spacing, minimal chrome.

## 3. Key screens

> This is the UX design spec. The shipped viewer implements its core — the board,
> eval bar, move list, the three modes, the adaptive readout, and the full
> Showcase (Colosseum, Tournament, Genomes Bonding, Analytics). Per-move clocks
> and the speed slider were descoped to keep the MVP focused.

### Home / Mode select
Three clear cards: **Watch AI vs AI**, **Play the Trained AI**, **Play the Adaptive AI**. Short one-line descriptions. Login/profile in the corner (optional for watching, required for adaptive).

### Game screen (shared layout)
```
+------------------------------------------------+
|  [White: Gen-50]   10:00        [eval bar]      |
|                                                 |
|            +------------------+                 |
|            |                  |   Move list     |
|            |   CHESS BOARD    |   1. e4  e5      |
|            |                  |   2. Nf3 Nc6     |
|            +------------------+   ...            |
|                                                 |
|  [Black: Gen-1]    09:43        controls        |
+------------------------------------------------+
```
- **Eval bar** (vertical, beside board): fills toward whoever's ahead; in AI-vs-AI it shows the *engine's own* judgment.
- **Clocks:** each runs only on that side's turn; pause on move. Low-time state turns red.
- **Move list:** scrollable, standard notation; click a move to jump (replay).
- **Controls:** play/pause, speed (showcase), new game, resign (player modes).

### AI vs AI showcase extras
- **Generation pickers** for White and Black ("Gen 1" … "Gen 50").
- **Speed slider** (1×–50×) for fast replays.
- **Strength curve** panel (win-rate vs baseline over generations) — the proof-of-learning centerpiece.

### Play vs Trained
- **Difficulty dial:** pick generation or search depth/time before starting.
- Clear turn indicator; legal-move hints toggle.

### Play vs Adaptive
- An **Adaptive** toggle, plus a live profile readout so the personalization is
  felt: games learned, positions known, recurring habits to punish, and a
  "sharpness" that climbs as the model sees more of your play.

### Auth / Profile
- Minimal sign-up/login (Supabase). Profile shows record, estimated rating, and games history with replay links.

## 4. Components

Board, eval bar, dual clock, move list, mode card, generation picker, speed slider, difficulty dial, strength-curve chart, result banner (checkmate/draw/time), auth forms, profile/stats panel.

## 5. Interaction & feedback

- Smooth piece movement; highlight last move and (for human) legal targets.
- Distinct, clear end states: "Checkmate — White wins," "Stalemate — draw," "Draw — perpetual check." (Plain repetition does not draw — a deliberate house rule; the engine plays on.)
- Loading states while weights/games fetch — never a frozen blank board.

## 6. Responsive

- **Desktop:** board centered, side panels (move list, eval, controls) flanking.
- **Mobile:** board on top full-width; move list/controls collapse below into tabs. Eval bar becomes a thin horizontal bar above the board.

## 7. Accessibility

- High contrast; don't rely on color alone (label whose turn it is in text, not just highlight).
- Keyboard navigable controls; ARIA labels on board squares and buttons.
- Respect reduced-motion: disable piece-slide animation when requested.

## 8. Out of scope (UI)

No 3D board, no sound-heavy experience, no theming engine for MVP — keep it one clean, well-executed look.
