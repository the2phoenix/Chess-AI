"use strict";

/* Darwin's Gambit — board viewer frontend.
 *
 * The browser is a thin client: python-chess (on the local server) owns all the
 * rules. This file renders the board from a FEN, handles click-to-move, asks the
 * server for legal targets and engine replies, and drives the AI-vs-AI watch
 * loop. No chess logic is duplicated here. */

const PIECE_GLYPH = {
  // Use the filled glyphs for both colours; CSS colours them.
  k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟",
};

const state = {
  mode: "play",            // "play" | "watch"
  fen: null,
  turn: "white",
  humanColor: "white",
  depth: 3,
  opponent: null,          // trained-AI ladder id (Play mode)
  opponents: [],           // ladder from /api/opponents
  adaptive: false,         // Mode F3: base engine + per-user exploit layer
  userId: "local",         // Supabase user id when signed in, else "local"
  learned: false,          // has the current game been folded into the model?
  pooled: false,           // has the current game been added to the experience pool?
  selected: null,          // square name, e.g. "e2"
  targets: [],             // legal targets for the selected piece
  lastMove: null,          // {from, to}
  checkSquare: null,
  moves: [],               // SAN history (for the move list)
  history: [],             // UCI history from the start — lets the server see
                           // the whole game and detect draw-by-repetition
  result: null,            // "1-0" | "0-1" | "1/2-1/2" once the game ends
  termination: null,       // human-readable end reason
  gameOver: false,
  busy: false,             // a request is in flight
  watching: false,         // AI-vs-AI loop running
};

const el = {
  board: document.getElementById("board"),
  evalFill: document.getElementById("evalFill"),
  evalText: document.getElementById("evalText"),
  statusLine: document.getElementById("statusLine"),
  thinking: document.getElementById("thinking"),
  moveList: document.getElementById("moveList"),
  modePlay: document.getElementById("modePlay"),
  modeWatch: document.getElementById("modeWatch"),
  colorCtl: document.getElementById("colorCtl"),
  colorSelect: document.getElementById("colorSelect"),
  depthSelect: document.getElementById("depthSelect"),
  depthCtl: document.getElementById("depthCtl"),
  opponentCtl: document.getElementById("opponentCtl"),
  opponentSelect: document.getElementById("opponentSelect"),
  opponentBlurb: document.getElementById("opponentBlurb"),
  adaptiveCtl: document.getElementById("adaptiveCtl"),
  adaptiveSelect: document.getElementById("adaptiveSelect"),
  adaptiveProfile: document.getElementById("adaptiveProfile"),
  newGame: document.getElementById("newGame"),
  watchStart: document.getElementById("watchStart"),
  watchPause: document.getElementById("watchPause"),
  saveGame: document.getElementById("saveGame"),
  myGames: document.getElementById("myGames"),
  gamesList: document.getElementById("gamesList"),
  promoOverlay: document.getElementById("promoOverlay"),
};

/* ----------------------------------------------------------------------- */
/* Networking                                                              */
/* ----------------------------------------------------------------------- */
// The engine API base. Empty = same origin (local dev: server.py serves both
// the page and /api). In production the static frontend (Vercel) and the engine
// backend (Render) live apart, so set window.DARWIN_API_BASE in app-config.js.
const API_BASE = (typeof window !== "undefined" && window.DARWIN_API_BASE) || "";

async function api(path, body) {
  const res = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const data = await res.json();
  if (data.error && !("ok" in data)) throw new Error(data.error);
  return data;
}

/* ----------------------------------------------------------------------- */
/* FEN parsing + board rendering                                           */
/* ----------------------------------------------------------------------- */
function parsePlacement(fen) {
  // Returns a map { "e4": "P", ... } from the placement field of a FEN.
  const placement = fen.split(" ")[0];
  const map = {};
  const ranks = placement.split("/");
  for (let r = 0; r < 8; r++) {
    const rankNo = 8 - r; // FEN starts at rank 8
    let file = 0;
    for (const ch of ranks[r]) {
      if (/\d/.test(ch)) {
        file += parseInt(ch, 10);
      } else {
        const sq = "abcdefgh"[file] + rankNo;
        map[sq] = ch;
        file++;
      }
    }
  }
  return map;
}

function orientation() {
  // White at the bottom unless the human is playing Black.
  return state.mode === "play" && state.humanColor === "black" ? "black" : "white";
}

function renderBoard() {
  const pieces = state.fen ? parsePlacement(state.fen) : {};
  const flip = orientation() === "black";
  el.board.innerHTML = "";

  const files = "abcdefgh".split("");
  const ranks = [8, 7, 6, 5, 4, 3, 2, 1];
  const fileOrder = flip ? [...files].reverse() : files;
  const rankOrder = flip ? [...ranks].reverse() : ranks;

  for (const rank of rankOrder) {
    for (const file of fileOrder) {
      const sq = file + rank;
      const fileIdx = files.indexOf(file);
      const isLight = (fileIdx + rank) % 2 === 1;

      const cell = document.createElement("div");
      cell.className = "square " + (isLight ? "light" : "dark");
      cell.dataset.square = sq;

      if (state.lastMove && (sq === state.lastMove.from || sq === state.lastMove.to)) {
        cell.classList.add("lastmove");
      }
      if (state.selected === sq) cell.classList.add("selected");
      if (state.checkSquare === sq) cell.classList.add("check");

      // legal-move hint
      const target = state.targets.find((t) => t.to === sq);
      if (target) {
        const hint = document.createElement("span");
        hint.className = "hint" + (target.capture ? " capture" : "");
        cell.appendChild(hint);
        cell.classList.add("clickable");
      }

      // piece
      const code = pieces[sq];
      if (code) {
        const span = document.createElement("span");
        const isWhite = code === code.toUpperCase();
        span.className = "piece " + (isWhite ? "white" : "black");
        span.textContent = PIECE_GLYPH[code.toLowerCase()];
        cell.appendChild(span);
        if (canSelect(sq, isWhite)) cell.classList.add("clickable");
      }

      // coordinate labels on the edges
      if (file === fileOrder[0]) addCoord(cell, "rank", rank);
      if (rank === rankOrder[rankOrder.length - 1]) addCoord(cell, "file", file);

      cell.addEventListener("click", () => onSquareClick(sq));
      el.board.appendChild(cell);
    }
  }
}

function addCoord(cell, kind, label) {
  const c = document.createElement("span");
  c.className = "coord " + kind;
  c.textContent = label;
  cell.appendChild(c);
}

function canSelect(sq, isWhitePiece) {
  if (state.mode !== "play" || state.gameOver || state.busy) return false;
  if (state.turn !== state.humanColor) return false;
  const humanIsWhite = state.humanColor === "white";
  return isWhitePiece === humanIsWhite;
}

/* ----------------------------------------------------------------------- */
/* Interaction                                                             */
/* ----------------------------------------------------------------------- */
async function onSquareClick(sq) {
  if (state.busy || state.gameOver || state.mode !== "play") return;
  if (state.turn !== state.humanColor) return;

  // Clicking a legal target completes a move.
  const target = state.targets.find((t) => t.to === sq);
  if (state.selected && target) {
    await makeHumanMove(state.selected, sq, target.promotion);
    return;
  }

  // Otherwise (re)select one of our pieces.
  const pieces = parsePlacement(state.fen);
  const code = pieces[sq];
  if (code) {
    const isWhite = code === code.toUpperCase();
    if (canSelect(sq, isWhite)) {
      state.selected = sq;
      const res = await api("/api/legal", { moves: state.history, square: sq });
      state.targets = res.targets || [];
      renderBoard();
      return;
    }
  }

  // Clicked empty/enemy with no selection → clear.
  state.selected = null;
  state.targets = [];
  renderBoard();
}

async function makeHumanMove(from, to, isPromotion) {
  let uci = from + to;
  if (isPromotion) {
    const piece = await askPromotion();
    if (!piece) return; // cancelled
    uci += piece;
  }

  state.selected = null;
  state.targets = [];
  setBusy(true);
  try {
    const res = await api("/api/move", { moves: state.history, uci });
    if (!res.ok) {
      setStatus("Illegal move — try again.");
      setBusy(false);
      renderBoard();
      return;
    }
    applyResult(res);

    if (!state.gameOver) {
      await engineReply();
    }
  } catch (err) {
    setStatus("Error: " + err.message);
  } finally {
    setBusy(false);
  }
}

async function engineReply() {
  setThinking(true);
  try {
    // Play mode faces the chosen *trained* opponent; watch mode uses depth.
    const body = { moves: state.history, depth: state.depth };
    if (state.mode === "play" && state.adaptive) {
      // Mode F3: the fixed-strong base engine + this user's exploit layer.
      body.adaptive = true;
      body.user = state.userId;
    } else if (state.mode === "play" && state.opponent) {
      body.opponent = state.opponent;
    }
    const res = await api("/api/engine", body);
    if (res.ok) {
      applyResult(res);
      if (res.profile) renderAdaptiveProfile(res.profile);
    }
  } finally {
    setThinking(false);
  }
}

/* Mode F3: after a game ends, fold the user's moves into their model so the
   adaptive AI sharpens next time. Idempotent per game via state.learned. */
async function maybeLearnGame() {
  if (!(state.mode === "play" && state.adaptive)) return;
  if (state.learned || !state.gameOver || state.history.length === 0) return;
  state.learned = true;
  try {
    const res = await api("/api/adaptive_learn", {
      user: state.userId,
      user_color: state.humanColor,
      moves: state.history,
    });
    if (res.ok && res.profile) renderAdaptiveProfile(res.profile);
  } catch (err) {
    /* learning is best-effort; never block play on it */
  }
}

function renderAdaptiveProfile(p) {
  if (!p) return;
  el.adaptiveProfile.classList.remove("hidden");
  const sharp = Math.round((p.difficulty || 0) * 100);
  el.adaptiveProfile.textContent =
    `Adaptive: ${p.games_seen} game(s) learned · ${p.positions_known} positions known · ` +
    `${p.recurring_mistakes} habit(s) to punish · sharpness ${sharp}%`;
}

async function refreshAdaptiveProfile() {
  try {
    const res = await api("/api/adaptive_profile", { user: state.userId });
    if (res.ok) renderAdaptiveProfile(res.profile);
  } catch (err) { /* ignore */ }
}

/* ----------------------------------------------------------------------- */
/* Watch mode (AI vs AI)                                                   */
/* ----------------------------------------------------------------------- */
async function watchLoop() {
  while (state.watching && !state.gameOver) {
    setThinking(true);
    let res;
    try {
      // variety: each AI-vs-AI game explores a fresh line, not one fixed game.
      res = await api("/api/engine", { moves: state.history, depth: state.depth, variety: true });
    } catch (err) {
      setStatus("Error: " + err.message);
      break;
    }
    setThinking(false);
    if (!res.ok) break;
    applyResult(res);
    // A short pause so the eye can follow the moves.
    await sleep(450);
  }
  state.watching = false;
  updateWatchButtons();
}

function startWatching() {
  if (state.gameOver) return;
  state.watching = true;
  updateWatchButtons();
  watchLoop();
}

function pauseWatching() {
  state.watching = false;
  updateWatchButtons();
}

/* ----------------------------------------------------------------------- */
/* Applying server results                                                 */
/* ----------------------------------------------------------------------- */
function applyResult(res) {
  state.fen = res.fen;
  state.turn = res.turn;
  state.gameOver = res.game_over;
  state.checkSquare = res.check_square || null;
  if (res.game_over) {
    state.result = res.result || null;
    state.termination = res.termination || null;
  }
  if (res.last_move) {
    state.lastMove = { from: res.last_move.slice(0, 2), to: res.last_move.slice(2, 4) };
  }
  if (res.san) state.moves.push(res.san);
  if (res.uci) state.history.push(res.uci);

  updateEvalBar(res.eval, res.game_over, res.result);
  renderMoveList();
  renderBoard();
  updateStatus(res);
  updateSaveButton();
  if (state.gameOver) {
    maybeLearnGame();
    contributeToPool();
  }
}

/* GSD §3: a finished human game also feeds the shared experience pool the
   offline pipeline trains on. Best-effort — play never depends on it. */
async function contributeToPool() {
  if (state.mode !== "play" || state.pooled || state.history.length === 0) return;
  state.pooled = true;
  const info = gameInfo();
  try {
    await api("/api/pool_add", {
      moves: state.history, white: info.white, black: info.black,
    });
  } catch (err) { /* ignore */ }
}

function updateStatus(res) {
  if (res.game_over) {
    const term = res.termination ? ` (${res.termination})` : "";
    let outcome;
    if (res.result === "1-0") outcome = "White wins";
    else if (res.result === "0-1") outcome = "Black wins";
    else outcome = "Draw";
    setStatus(`Game over — ${outcome}${term}.`);
    return;
  }
  const side = res.turn === "white" ? "White" : "Black";
  const check = res.in_check ? " — check!" : "";
  if (state.mode === "play") {
    const who = res.turn === state.humanColor ? "Your move" : "Engine to move";
    setStatus(`${who} (${side})${check}`);
  } else {
    setStatus(`${side} to move${check}`);
  }
}

function updateEvalBar(centipawns, gameOver, result) {
  let cp = centipawns || 0;
  // Map centipawns (White's view) to a 0–100% fill via a soft sigmoid.
  let pct;
  if (Math.abs(cp) >= 100000 || (gameOver && result && result !== "1/2-1/2")) {
    pct = (result === "0-1" || cp < 0) ? 2 : 98;
  } else {
    pct = 100 / (1 + Math.exp(-cp / 350));
  }
  el.evalFill.style.height = pct.toFixed(1) + "%";

  let label;
  if (gameOver) {
    label = result === "1-0" ? "1-0" : result === "0-1" ? "0-1" : "½";
  } else {
    const pawns = cp / 100;
    label = (pawns >= 0 ? "+" : "") + pawns.toFixed(1);
  }
  el.evalText.textContent = label;
}

function renderMoveList() {
  el.moveList.innerHTML = "";
  for (let i = 0; i < state.moves.length; i += 2) {
    const num = document.createElement("li");
    num.className = "num";
    num.textContent = (i / 2 + 1) + ".";
    el.moveList.appendChild(num);

    const white = document.createElement("li");
    white.className = "san";
    white.textContent = state.moves[i] || "";
    el.moveList.appendChild(white);

    const black = document.createElement("li");
    black.className = "san";
    black.textContent = state.moves[i + 1] || "";
    el.moveList.appendChild(black);
  }
  // highlight the latest move
  const sans = el.moveList.querySelectorAll(".san");
  if (sans.length) sans[sans.length - 1].classList.add("last");
  el.moveList.scrollTop = el.moveList.scrollHeight;
}

/* ----------------------------------------------------------------------- */
/* Promotion picker                                                        */
/* ----------------------------------------------------------------------- */
function askPromotion() {
  return new Promise((resolve) => {
    el.promoOverlay.classList.remove("hidden");
    const buttons = el.promoOverlay.querySelectorAll(".promo-piece");
    const handler = (e) => {
      cleanup();
      resolve(e.currentTarget.dataset.piece);
    };
    const onBackdrop = (e) => {
      if (e.target === el.promoOverlay) {
        cleanup();
        resolve(null);
      }
    };
    function cleanup() {
      el.promoOverlay.classList.add("hidden");
      buttons.forEach((b) => b.removeEventListener("click", handler));
      el.promoOverlay.removeEventListener("click", onBackdrop);
    }
    buttons.forEach((b) => b.addEventListener("click", handler));
    el.promoOverlay.addEventListener("click", onBackdrop);
  });
}

/* ----------------------------------------------------------------------- */
/* UI helpers                                                              */
/* ----------------------------------------------------------------------- */
function setStatus(text) { el.statusLine.textContent = text; }
function setThinking(on) { el.thinking.classList.toggle("hidden", !on); }
function setBusy(on) { state.busy = on; }
function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

function updateWatchButtons() {
  if (state.mode !== "watch") {
    el.watchStart.classList.add("hidden");
    el.watchPause.classList.add("hidden");
    return;
  }
  el.watchStart.classList.toggle("hidden", state.watching);
  el.watchPause.classList.toggle("hidden", !state.watching);
  el.watchStart.disabled = state.gameOver;
}

/* ----------------------------------------------------------------------- */
/* New game + mode switching                                               */
/* ----------------------------------------------------------------------- */
async function newGame() {
  pauseWatching();
  state.depth = parseInt(el.depthSelect.value, 10);
  state.opponent = el.opponentSelect.value || null;
  state.adaptive = el.adaptiveSelect.value === "on";
  state.userId = (window.DarwinCloud && window.DarwinCloud.user && window.DarwinCloud.user.id) || "local";
  state.learned = false;
  state.pooled = false;
  state.humanColor = el.colorSelect.value;
  state.selected = null;
  state.targets = [];
  state.lastMove = null;
  state.checkSquare = null;
  state.moves = [];
  state.history = [];
  state.gameOver = false;
  state.result = null;
  state.termination = null;

  const res = await api("/api/new", {});
  state.fen = res.fen;
  state.turn = res.turn;
  updateEvalBar(res.eval, false, null);
  renderMoveList();
  renderBoard();
  updateStatus(res);
  updateWatchButtons();
  updateSaveButton();

  // If the human chose Black, let the engine (White) open.
  if (state.mode === "play" && state.humanColor === "black") {
    setBusy(true);
    await engineReply();
    setBusy(false);
  }
}

function setMode(mode) {
  state.mode = mode;
  el.modePlay.classList.toggle("active", mode === "play");
  el.modeWatch.classList.toggle("active", mode === "watch");
  el.colorCtl.classList.toggle("hidden", mode === "watch");
  // Play mode picks a trained opponent; watch mode picks a raw depth.
  el.opponentCtl.classList.toggle("hidden", mode === "watch");
  el.opponentBlurb.classList.toggle("hidden", mode === "watch");
  el.adaptiveCtl.classList.toggle("hidden", mode === "watch");
  el.adaptiveProfile.classList.add("hidden");
  el.depthCtl.classList.toggle("hidden", mode === "play");
  applyAdaptiveUI();
  el.newGame.classList.toggle("hidden", false);
  el.watchStart.classList.toggle("hidden", mode !== "watch");
  el.watchPause.classList.add("hidden");
  newGame();
}

/* ----------------------------------------------------------------------- */
/* Wire up + boot                                                          */
/* ----------------------------------------------------------------------- */
function showOpponentBlurb() {
  const opp = state.opponents.find((o) => o.id === el.opponentSelect.value);
  el.opponentBlurb.textContent = opp ? opp.blurb : "";
}

/* Adaptive (Mode F3) UI: when on, the base is a fixed-strong engine, so the
   opponent ladder doesn't apply — dim it and show the per-user profile. */
function applyAdaptiveUI() {
  const on = el.adaptiveSelect.value === "on" && state.mode === "play";
  state.adaptive = on;
  el.opponentSelect.disabled = on;
  el.opponentCtl.style.opacity = on ? "0.4" : "";
  if (on) {
    state.userId = (window.DarwinCloud && window.DarwinCloud.user && window.DarwinCloud.user.id) || "local";
    el.opponentBlurb.textContent =
      "Adaptive: a fixed-strong base engine that learns and exploits your habits — it sharpens the more you play. The base engine is never weakened.";
    refreshAdaptiveProfile();
  } else if (state.mode === "play") {
    el.adaptiveProfile.classList.add("hidden");
    showOpponentBlurb();
  }
}

async function loadOpponents() {
  try {
    const data = await api("/api/opponents", {});
    state.opponents = data.opponents || [];
    el.opponentSelect.innerHTML = "";
    for (const opp of state.opponents) {
      const o = document.createElement("option");
      o.value = opp.id;
      o.textContent = opp.label;
      el.opponentSelect.appendChild(o);
    }
    if (data.default) el.opponentSelect.value = data.default;
    state.opponent = el.opponentSelect.value || null;
    if (!data.trained) {
      el.opponentBlurb.textContent =
        "No evolved run found — facing the hand-tuned default. Run training/make_opponents.py to play the trained AI.";
    } else {
      showOpponentBlurb();
    }
  } catch (err) {
    el.opponentBlurb.textContent = "Could not load opponents: " + err.message;
  }
}

el.modePlay.addEventListener("click", () => setMode("play"));
el.modeWatch.addEventListener("click", () => setMode("watch"));
el.newGame.addEventListener("click", newGame);
el.watchStart.addEventListener("click", startWatching);
el.watchPause.addEventListener("click", pauseWatching);
el.depthSelect.addEventListener("change", () => { state.depth = parseInt(el.depthSelect.value, 10); });
el.opponentSelect.addEventListener("change", () => {
  state.opponent = el.opponentSelect.value || null;
  showOpponentBlurb();
});
el.adaptiveSelect.addEventListener("change", applyAdaptiveUI);

/* ----------------------------------------------------------------------- */
/* Cloud: save games to the signed-in user's account (Supabase + RLS)      */
/* ----------------------------------------------------------------------- */
function gameInfo() {
  if (state.mode === "watch") {
    return { mode: "ai_vs_ai", white: "Darwin (White)", black: "Darwin (Black)", opponent: null };
  }
  if (state.adaptive) {
    const label = "Adaptive AI";
    return state.humanColor === "white"
      ? { mode: "vs_adaptive", white: "You", black: label, opponent: null }
      : { mode: "vs_adaptive", white: label, black: "You", opponent: null };
  }
  const opp = state.opponents.find((o) => o.id === state.opponent);
  const label = (opp && opp.label) || state.opponent || "Engine";
  return state.humanColor === "white"
    ? { mode: "vs_trained", white: "You", black: label, opponent: state.opponent }
    : { mode: "vs_trained", white: label, black: "You", opponent: state.opponent };
}

function buildPGN(white, black, mode) {
  const result = state.result || "*";
  const date = new Date().toISOString().slice(0, 10).replace(/-/g, ".");
  let pgn =
    `[Event "Darwin's Gambit"]\n[Site "Darwin's Gambit viewer"]\n[Date "${date}"]\n` +
    `[White "${white}"]\n[Black "${black}"]\n[Result "${result}"]\n[Mode "${mode}"]\n\n`;
  let body = "";
  for (let i = 0; i < state.moves.length; i += 2) {
    body += `${i / 2 + 1}. ${state.moves[i]}${state.moves[i + 1] ? " " + state.moves[i + 1] : ""} `;
  }
  return (pgn + body.trim() + " " + result).trim();
}

function updateSaveButton() {
  const cloud = window.DarwinCloud;
  const can = cloud && cloud.enabled && cloud.user && state.gameOver && state.moves.length > 0;
  el.saveGame.classList.toggle("hidden", !can);
}

async function saveCurrentGame() {
  const cloud = window.DarwinCloud;
  if (!cloud || !cloud.user) return;
  const info = gameInfo();
  el.saveGame.disabled = true;
  try {
    await cloud.saveGame({
      mode: info.mode,
      opponent: info.opponent,
      white: info.white,
      black: info.black,
      result: state.result || null,
      termination: state.termination || null,
      plies: state.moves.length,
      pgn: buildPGN(info.white, info.black, info.mode),
    });
    setStatus("Game saved to your account.");
    await refreshGames();
  } catch (err) {
    setStatus("Save failed: " + (err.message || err));
  } finally {
    el.saveGame.disabled = false;
    updateSaveButton();
  }
}

async function refreshGames() {
  const cloud = window.DarwinCloud;
  if (!cloud || !cloud.enabled || !cloud.user) {
    el.myGames.classList.add("hidden");
    return;
  }
  el.myGames.classList.remove("hidden");
  let games = [];
  try { games = await cloud.listGames(); } catch (e) { return; }
  el.gamesList.innerHTML = "";
  if (!games.length) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "No saved games yet.";
    el.gamesList.appendChild(li);
    return;
  }
  for (const g of games) {
    const li = document.createElement("li");
    const date = new Date(g.created_at).toLocaleString();
    li.innerHTML =
      `<span class="g-main">${g.white} vs ${g.black} — ${g.result || "*"}</span>` +
      `<span class="g-sub">${g.mode} · ${date}</span>`;
    li.title = "Click to copy this game's PGN";
    li.addEventListener("click", () => {
      try { navigator.clipboard.writeText(g.pgn); setStatus("PGN copied to clipboard."); }
      catch (e) { window.prompt("PGN:", g.pgn); }
    });
    el.gamesList.appendChild(li);
  }
}

el.saveGame.addEventListener("click", saveCurrentGame);

// DarwinCloud is defined by the auth module, which loads after this script.
function initCloud() {
  const cloud = window.DarwinCloud;
  if (!cloud) { setTimeout(initCloud, 120); return; }
  cloud.onChange(() => { updateSaveButton(); refreshGames(); });
  updateSaveButton();
  refreshGames();
}

(async function boot() {
  await loadOpponents();
  newGame();
  initCloud();
})();
