"use strict";

/* Darwin's Gambit — evolution showcase.
 *
 * Pure static replay: everything is read from showcase.json (positions, evals,
 * breeding lineage). No engine runs in the browser — so this same page deploys
 * to a static host unchanged. */

const PIECE_GLYPH = { k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟" };
const WEIGHT_MAX = 3.0; // gene-bar scale (matches the GA's weight ceiling)

let DATA = null;

/* ---------- tiny DOM + board helpers ---------- */
function el(tag, cls) { const e = document.createElement(tag); if (cls) e.className = cls; return e; }
function $(id) { return document.getElementById(id); }

function parsePlacement(fen) {
  const map = {};
  const ranks = fen.split(" ")[0].split("/");
  for (let r = 0; r < 8; r++) {
    const rankNo = 8 - r;
    let file = 0;
    for (const ch of ranks[r]) {
      if (/\d/.test(ch)) file += parseInt(ch, 10);
      else { map["abcdefgh"[file] + rankNo] = ch; file++; }
    }
  }
  return map;
}

function renderBoard(container, fen) {
  const pieces = parsePlacement(fen);
  container.innerHTML = "";
  const files = "abcdefgh".split("");
  for (let rank = 8; rank >= 1; rank--) {
    for (let f = 0; f < 8; f++) {
      const sq = files[f] + rank;
      const cell = el("div", "sq " + ((f + rank) % 2 === 1 ? "light" : "dark"));
      const code = pieces[sq];
      if (code) {
        const isWhite = code === code.toUpperCase();
        const pc = el("span", "pc " + (isWhite ? "w" : "b"));
        pc.textContent = PIECE_GLYPH[code.toLowerCase()];
        cell.appendChild(pc);
      }
      container.appendChild(cell);
    }
  }
}

function resultCode(g) {
  return g.result === "1-0" ? "1-0" : g.result === "0-1" ? "0-1" : "½";
}
function resultWinner(g) {
  if (g.result === "1-0") return `${g.white_id} wins`;
  if (g.result === "0-1") return `${g.black_id} wins`;
  return "draw";
}

/* ===================================================================== */
/* COLOSSEUM                                                             */
/* ===================================================================== */
const col = { gen: 0, tick: 0, timer: null, maxLen: 1, boards: [] };

function buildColosseum() {
  const gen = DATA.generations[col.gen];
  const grid = $("colGrid");
  grid.innerHTML = "";
  col.boards = [];
  col.maxLen = 1;
  for (const game of gen.games) {
    col.maxLen = Math.max(col.maxLen, game.fens.length);
    const card = el("div", "game-card");
    const names = el("div", "names");
    names.innerHTML = `<span>${game.white_id}</span><span>vs</span><span>${game.black_id}</span>`;
    const board = el("div", "board");
    const badge = el("div", "badge");
    card.append(names, board, badge);
    card.addEventListener("click", () => openFeatured(game));
    grid.appendChild(card);
    col.boards.push({ game, board, card, badge });
  }
  col.tick = 0;
  renderColTick();
}

function renderColTick() {
  for (const b of col.boards) {
    const idx = Math.min(col.tick, b.game.fens.length - 1);
    renderBoard(b.board, b.game.fens[idx]);
    const done = idx >= b.game.fens.length - 1;
    b.card.classList.toggle("done", done);
    if (done) b.badge.textContent = resultCode(b.game);
  }
  $("colStatus").textContent = `ply ${Math.min(col.tick, col.maxLen - 1)} / ${col.maxLen - 1}`;
}

function stopCol() {
  if (col.timer) { clearInterval(col.timer); col.timer = null; }
  $("colPlay").textContent = "▶ Play all";
}
function playCol() {
  if (col.timer) { stopCol(); return; }
  if (col.tick >= col.maxLen - 1) col.tick = 0;
  $("colPlay").textContent = "⏸ Pause";
  const tickMs = 1000 / parseInt($("colSpeed").value, 10);
  col.timer = setInterval(() => {
    if (col.tick >= col.maxLen - 1) { stopCol(); return; }
    col.tick++;
    renderColTick();
  }, tickMs);
}

/* ===================================================================== */
/* FEATURED GAME (eval bar + clock)                                      */
/* ===================================================================== */
const feat = { game: null, idx: 0, timer: null };

function openFeatured(game) {
  feat.game = game; feat.idx = 0;
  $("featTitle").textContent = `${game.white_id} (White)  vs  ${game.black_id} (Black)`;
  $("featScrub").max = String(game.fens.length - 1);
  renderFeat();
  $("featured").classList.remove("hidden");
}
function closeFeatured() {
  stopFeat();
  $("featured").classList.add("hidden");
}
function renderFeat() {
  const g = feat.game, i = feat.idx;
  renderBoard($("featBoard"), g.fens[i]);
  const cp = g.evals[i];
  const pct = 100 / (1 + Math.exp(-cp / 350));
  $("featEvalFill").style.height = pct.toFixed(1) + "%";
  $("featEvalText").textContent = (cp >= 0 ? "+" : "") + (cp / 100).toFixed(1);
  $("featClock").textContent = `move ${Math.ceil(i / 2)} · ply ${i}/${g.fens.length - 1}`;
  $("featScrub").value = String(i);
  const done = i >= g.fens.length - 1;
  $("featResult").textContent = done ? `${g.result} — ${resultWinner(g)} (${g.termination})` : "";
}
function stopFeat() {
  if (feat.timer) { clearInterval(feat.timer); feat.timer = null; }
  $("featPlay").textContent = "▶";
}
function playFeat() {
  if (feat.timer) { stopFeat(); return; }
  if (feat.idx >= feat.game.fens.length - 1) feat.idx = 0;
  $("featPlay").textContent = "⏸";
  feat.timer = setInterval(() => {
    if (feat.idx >= feat.game.fens.length - 1) { stopFeat(); return; }
    feat.idx++;
    renderFeat();
  }, 550);
}

/* ===================================================================== */
/* GENOMES BONDING                                                       */
/* ===================================================================== */
const bond = { genIdx: 0, step: 0, timer: null };

function geneRow(name, value, fillClass, mutated) {
  const row = el("div", "gene-row" + (mutated ? " spark" : ""));
  const label = el("div", "gene-name"); label.textContent = name;
  const track = el("div", "gene-track");
  const fill = el("div", "gene-fill " + fillClass + (mutated ? " mutated" : ""));
  // start at 0 then grow on next frame for the animation
  requestAnimationFrame(() => {
    fill.style.width = Math.min(100, (value / WEIGHT_MAX) * 100).toFixed(1) + "%";
  });
  track.appendChild(fill);
  const val = el("div", "gene-val"); val.textContent = value.toFixed(2);
  row.append(label, track, val);
  return row;
}

function genomeCard(title, vector, cls, perGeneClass, mutatedSet) {
  const card = el("div", "genome-card " + cls);
  const h = el("h3"); h.textContent = title; card.appendChild(h);
  DATA.gene_names.forEach((name, i) => {
    const fillClass = perGeneClass ? perGeneClass(i) : (cls === "parentA" ? "fromA" : "fromB");
    card.appendChild(geneRow(name, vector[i], fillClass, mutatedSet ? mutatedSet.has(i) : false));
  });
  return card;
}

function renderBonding() {
  const gen = DATA.generations[bond.genIdx];
  const breedings = gen.breedings;
  const stage = $("bondStage");
  stage.innerHTML = "";
  if (!breedings.length) {
    stage.textContent = "No breeding recorded for this transition.";
    return;
  }
  bond.step = Math.max(0, Math.min(bond.step, breedings.length - 1));
  const b = breedings[bond.step];
  const mutatedSet = new Set(b.mutations.map((m) => DATA.gene_names.indexOf(m.gene)));

  const left = genomeCard(`Parent A · ${b.parent_a_id}`, b.parent_a_vector, "parentA");
  const right = genomeCard(`Parent B · ${b.parent_b_id}`, b.parent_b_vector, "parentB");

  const middle = el("div", "bond-middle");
  middle.innerHTML = `<div class="bond-arrow">⇣</div>`;
  const child = genomeCard(
    `Child · ${b.child_id}`,
    b.child_vector,
    "child",
    (i) => (b.crossover_mask[i] ? "fromB" : "fromA"),
    mutatedSet
  );
  middle.appendChild(child);
  const meta = el("div", "bond-meta");
  meta.innerHTML =
    `breeding ${bond.step + 1} / ${breedings.length} · ` +
    `<span style="color:var(--parentA)">■</span> from A &nbsp; ` +
    `<span style="color:var(--parentB)">■</span> from B &nbsp; ` +
    `<span style="color:var(--gold)">▣</span> mutated (${b.mutations.length})`;
  middle.appendChild(meta);

  stage.append(left, middle, right);
  $("bondStatus").textContent =
    `Gen ${bond.genIdx} → Gen ${bond.genIdx + 1}`;
}

function stopBond() {
  if (bond.timer) { clearInterval(bond.timer); bond.timer = null; }
  $("bondPlay").textContent = "▶ Play all";
}
function playBond() {
  if (bond.timer) { stopBond(); return; }
  const breedings = DATA.generations[bond.genIdx].breedings;
  $("bondPlay").textContent = "⏸ Pause";
  bond.timer = setInterval(() => {
    if (bond.step >= breedings.length - 1) { stopBond(); return; }
    bond.step++;
    renderBonding();
  }, 1600);
}

/* ===================================================================== */
/* EVOLUTION CURVE                                                       */
/* ===================================================================== */
function renderCurve() {
  const gens = DATA.generations;
  const W = 880, H = 340, padL = 50, padR = 20, padT = 24, padB = 40;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const n = gens.length;
  const x = (i) => padL + (n === 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const y = (v) => padT + (1 - v) * innerH;

  const pts = gens.map((g, i) => [x(i), y(g.benchmark_winrate)]);
  const poly = pts.map((p) => p.join(",")).join(" ");

  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="strength curve">`;
  // gridlines + y labels (0, 25, 50, 75, 100%)
  for (let v = 0; v <= 1.0001; v += 0.25) {
    const yy = y(v).toFixed(1);
    const isBase = Math.abs(v - 0.5) < 1e-6;
    svg += `<line x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}" stroke="${isBase ? "#d9b24a" : "#2e3426"}" stroke-dasharray="${isBase ? "6 5" : "0"}"/>`;
    svg += `<text x="${padL - 8}" y="${(+yy + 4).toFixed(1)}" fill="#9aa089" font-size="12" text-anchor="end">${Math.round(v * 100)}%</text>`;
  }
  svg += `<text x="${W - padR}" y="${(y(0.5) - 6).toFixed(1)}" fill="#d9b24a" font-size="11" text-anchor="end">baseline 50%</text>`;
  // x labels
  gens.forEach((g, i) => {
    svg += `<text x="${x(i).toFixed(1)}" y="${H - 14}" fill="#9aa089" font-size="12" text-anchor="middle">G${i}</text>`;
  });
  // the line + points
  svg += `<polyline points="${poly}" fill="none" stroke="#8fbf6b" stroke-width="2.5"/>`;
  pts.forEach((p, i) => {
    const wr = (gens[i].benchmark_winrate * 100).toFixed(0);
    svg += `<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="5" fill="#11140f" stroke="#d9b24a" stroke-width="2" class="cpt" data-gen="${i}" style="cursor:pointer"/>`;
    svg += `<text x="${p[0].toFixed(1)}" y="${(p[1] - 12).toFixed(1)}" fill="#e9ead8" font-size="11" text-anchor="middle">${wr}%</text>`;
  });
  svg += `</svg>`;
  $("curveWrap").innerHTML = svg;

  $("curveWrap").querySelectorAll(".cpt").forEach((c) => {
    c.addEventListener("click", () => {
      col.gen = parseInt(c.dataset.gen, 10);
      $("colGen").value = String(col.gen);
      switchTab("colosseum");
      buildColosseum();
    });
  });

  // best genome vs baseline panel
  const panel = $("bestPanel");
  panel.innerHTML = "";
  panel.appendChild(genomeCard(`Champion · ${DATA.best.id}`, DATA.best.vector, "child",
    () => "fromB"));
  panel.appendChild(genomeCard("Baseline (hand-tuned)", DATA.baseline, "parentA",
    () => "fromA"));
}

/* ===================================================================== */
/* TOURNAMENT OF CHAMPIONS                                               */
/* ===================================================================== */
let TOURNEY = null;
const tour = { timer: null };

function matchGame(m) {
  // Adapt a bracket match to the featured-game shape (reuses the modal).
  return {
    white_id: m.a.label, black_id: m.b.label,
    fens: m.fens, evals: m.evals, result: m.result,
    termination: "tournament match",
  };
}

function renderBracket(revealRounds) {
  const wrap = $("bracket");
  wrap.innerHTML = "";
  if (!TOURNEY) { wrap.textContent = "No tournament yet — run training/tournament_data.py."; return; }

  TOURNEY.rounds.forEach((round, ri) => {
    const col = el("div", "bracket-round");
    const label = el("div", "round-label");
    label.textContent = round.is_final ? "Final" : `Round ${ri + 1}`;
    col.appendChild(label);

    round.matches.forEach((m) => {
      const card = el("div", "match" + (round.is_final ? " final" : ""));
      const shown = revealRounds === undefined || ri < revealRounds;
      if (!shown) card.classList.add("pending");

      const aWin = m.winner_id === m.a.id, bWin = m.winner_id === m.b.id;
      const a = el("div", "competitor" + (shown ? (aWin ? " win" : " lose") : ""));
      a.innerHTML = `<span>${m.a.label}</span><span class="score">${shown ? (m.result === "1-0" ? "1" : m.result === "0-1" ? "0" : "½") : ""}</span>`;
      const b = el("div", "competitor" + (shown ? (bWin ? " win" : " lose") : ""));
      b.innerHTML = `<span>${m.b.label}</span><span class="score">${shown ? (m.result === "0-1" ? "1" : m.result === "1-0" ? "0" : "½") : ""}</span>`;
      card.append(a, b);

      if (shown && m.merge) {
        const note = el("div", "merge-note");
        note.textContent = `⚇ ${m.merge.winner_label} absorbs ${m.merge.loser_label} → hybrid` +
          (m.merge.mutations.length ? ` (+${m.merge.mutations.length} mut)` : "");
        card.appendChild(note);
      }
      card.title = "Click to replay this game";
      card.addEventListener("click", () => openFeatured(matchGame(m)));
      col.appendChild(card);
    });
    wrap.appendChild(col);
  });

  // Champion column
  const champ = TOURNEY.champion;
  if (champ && (revealRounds === undefined || revealRounds > TOURNEY.rounds.length)) {
    const col = el("div", "bracket-champ");
    col.innerHTML = `<div class="crown">👑</div><div class="name">${champ.label}</div>`;
    wrap.appendChild(col);
    showChampBanner(champ);
  } else {
    $("champBanner").classList.add("hidden");
  }
}

function showChampBanner(champ) {
  const b = $("champBanner");
  b.classList.remove("hidden");
  const genes = DATA.gene_names.map((n, i) =>
    `<span class="cg">${n} <b>${champ.vector[i].toFixed(2)}</b></span>`).join("");
  b.innerHTML = `<h2>👑 Ultimate champion: ${champ.label}</h2>` +
    `<div class="champ-sub">Survived the knockout, absorbing every opponent it beat.</div>` +
    `<div class="champ-genes">${genes}</div>`;
}

function stopTour() { if (tour.timer) { clearInterval(tour.timer); tour.timer = null; } $("tourPlay").textContent = "▶ Run tournament"; }

function playTournament() {
  if (!TOURNEY) return;
  if (tour.timer) { stopTour(); return; }
  $("tourPlay").textContent = "⏸ Pause";
  let reveal = 0;
  const total = TOURNEY.rounds.length + 1;
  renderBracket(reveal);
  $("tourStatus").textContent = "";
  tour.timer = setInterval(() => {
    reveal++;
    renderBracket(reveal);
    $("tourStatus").textContent = reveal > TOURNEY.rounds.length
      ? "Champion crowned!" : `Round ${reveal} decided`;
    if (reveal >= total) { stopTour(); }
  }, 1400);
}

/* ===================================================================== */
/* ANALYTICS (computed from the generations data)                       */
/* ===================================================================== */
const SERIES_COLORS = ["#8fbf6b", "#6fa8dc", "#e0a458", "#d3705f", "#b388e0"];

function multiLineChart(container, series, yMin, yMax, fmt) {
  const W = 880, H = 300, padL = 50, padR = 20, padT = 18, padB = 36;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const n = series[0] ? series[0].points.length : 0;
  const x = (i) => padL + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const y = (v) => padT + (1 - (v - yMin) / (yMax - yMin || 1)) * innerH;

  let svg = `<svg viewBox="0 0 ${W} ${H}">`;
  for (let k = 0; k <= 4; k++) {
    const v = yMin + (k / 4) * (yMax - yMin);
    const yy = y(v).toFixed(1);
    svg += `<line x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}" stroke="#2e3426"/>`;
    svg += `<text x="${padL - 8}" y="${(+yy + 4)}" fill="#9aa089" font-size="11" text-anchor="end">${fmt(v)}</text>`;
  }
  for (let i = 0; i < n; i++)
    svg += `<text x="${x(i).toFixed(1)}" y="${H - 12}" fill="#9aa089" font-size="11" text-anchor="middle">G${i}</text>`;
  for (const s of series) {
    const poly = s.points.map((p, i) => `${x(i).toFixed(1)},${y(p).toFixed(1)}`).join(" ");
    svg += `<polyline points="${poly}" fill="none" stroke="${s.color}" stroke-width="2.2"/>`;
    s.points.forEach((p, i) => { svg += `<circle cx="${x(i).toFixed(1)}" cy="${y(p).toFixed(1)}" r="3" fill="${s.color}"/>`; });
  }
  svg += `</svg>`;
  const legend = `<div class="legend">` + series.map((s) =>
    `<span class="key"><span class="swatch" style="background:${s.color}"></span>${s.label}</span>`).join("") + `</div>`;
  container.innerHTML = svg + legend;
}

function renderSummary() {
  const gens = DATA.generations;
  const wrs = gens.map((g) => g.benchmark_winrate);
  const first = wrs[0], best = Math.max(...wrs);
  const champGen = gens.find((g) => g.benchmark_winrate === best);
  $("evoSummary").innerHTML = `
    <div class="stat"><div class="big">${(first * 100).toFixed(0)}% → ${(best * 100).toFixed(0)}%</div><div class="lbl">win-rate vs baseline (Gen 0 → best)</div></div>
    <div class="stat"><div class="big">+${((best - first) * 100).toFixed(0)} pts</div><div class="lbl">strength gained through evolution</div></div>
    <div class="stat"><div class="big">${gens.length}</div><div class="lbl">generations evolved</div></div>
    <div class="stat"><div class="big">${DATA.best.id}</div><div class="lbl">overall champion genome</div></div>`;
}

function renderFitnessChart() {
  const gens = DATA.generations;
  const best = [], avg = [], min = [];
  for (const g of gens) {
    const fits = g.population.map((p) => p.fitness);
    best.push(Math.max(...fits));
    min.push(Math.min(...fits));
    avg.push(fits.reduce((a, b) => a + b, 0) / fits.length);
  }
  const hi = Math.max(...best) || 1;
  multiLineChart($("fitnessWrap"), [
    { label: "best", color: SERIES_COLORS[0], points: best },
    { label: "average", color: SERIES_COLORS[1], points: avg },
    { label: "weakest", color: SERIES_COLORS[3], points: min },
  ], 0, hi, (v) => v.toFixed(0));
}

function renderGenesChart() {
  const gens = DATA.generations;
  const series = DATA.gene_names.map((name, gi) => ({
    label: name, color: SERIES_COLORS[gi % SERIES_COLORS.length],
    points: gens.map((g) => g.best_vector[gi]),
  }));
  let hi = 0;
  for (const s of series) hi = Math.max(hi, ...s.points);
  multiLineChart($("genesWrap"), series, 0, Math.max(1, Math.ceil(hi)), (v) => v.toFixed(1));
}

function renderEvolution() {
  renderSummary();
  renderCurve();        // strength curve + champion-vs-baseline panel (existing)
  renderFitnessChart();
  renderGenesChart();
}

/* ===================================================================== */
/* TABS + BOOT                                                           */
/* ===================================================================== */
function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("hidden", v.id !== name));
  stopCol(); stopBond(); stopTour();
}

function populateSelectors() {
  const colGen = $("colGen");
  DATA.generations.forEach((g, i) => {
    const o = el("option"); o.value = String(i);
    o.textContent = `Gen ${i}  (best ${(g.benchmark_winrate * 100).toFixed(0)}% vs baseline)`;
    colGen.appendChild(o);
  });
  const bondGen = $("bondGen");
  for (let i = 0; i < DATA.generations.length - 1; i++) {
    const o = el("option"); o.value = String(i);
    o.textContent = `Gen ${i} → Gen ${i + 1}`;
    bondGen.appendChild(o);
  }
}

function wireEvents() {
  document.querySelectorAll(".tab").forEach((t) =>
    t.addEventListener("click", () => switchTab(t.dataset.tab)));

  $("colGen").addEventListener("change", (e) => { stopCol(); col.gen = parseInt(e.target.value, 10); buildColosseum(); });
  $("colPlay").addEventListener("click", playCol);
  $("colRestart").addEventListener("click", () => { stopCol(); col.tick = 0; renderColTick(); });
  $("colSpeed").addEventListener("change", () => { if (col.timer) { stopCol(); playCol(); } });

  $("featClose").addEventListener("click", closeFeatured);
  $("featPlay").addEventListener("click", playFeat);
  $("featRestart").addEventListener("click", () => { stopFeat(); feat.idx = 0; renderFeat(); });
  $("featScrub").addEventListener("input", (e) => { stopFeat(); feat.idx = parseInt(e.target.value, 10); renderFeat(); });
  $("featured").addEventListener("click", (e) => { if (e.target === $("featured")) closeFeatured(); });

  $("bondGen").addEventListener("change", (e) => { stopBond(); bond.genIdx = parseInt(e.target.value, 10); bond.step = 0; renderBonding(); });
  $("bondPrev").addEventListener("click", () => { stopBond(); bond.step--; renderBonding(); });
  $("bondNext").addEventListener("click", () => { stopBond(); bond.step++; renderBonding(); });
  $("bondPlay").addEventListener("click", playBond);

  $("tourPlay").addEventListener("click", playTournament);
  $("tourReveal").addEventListener("click", () => { stopTour(); renderBracket(); });
}

async function boot() {
  try {
    const res = await fetch("showcase.json");
    DATA = await res.json();
  } catch (err) {
    $("loading").textContent = "Could not load showcase.json — run training/showcase_data.py first.";
    return;
  }
  // Tournament data is optional (generated separately).
  try {
    const tr = await fetch("tournament.json");
    if (tr.ok) TOURNEY = await tr.json();
  } catch (e) { /* no tournament yet */ }

  $("loading").classList.add("hidden");
  populateSelectors();
  wireEvents();
  buildColosseum();
  renderBonding();
  renderEvolution();
  renderBracket();
}

boot();
