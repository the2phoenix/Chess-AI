/* Darwin's Gambit — Supabase auth + cloud storage (Phase 5).
 *
 * Loaded as an ES module. Talks to Supabase directly from the browser using the
 * PUBLIC anon key; Row Level Security (supabase/schema.sql) is what actually
 * protects data so a user only ever sees their own rows. No service-role key is
 * ever used here.
 *
 * The Supabase library is imported *lazily* — only once the project is
 * configured — so an unconfigured or offline viewer still works for playing and
 * shows a clear message. Exposes `window.DarwinCloud` for app.js. */

const cfg = window.SUPABASE_CONFIG || {};
const CONFIGURED =
  !!cfg.url && !cfg.url.includes("YOUR-PROJECT") &&
  !!cfg.anonKey && !cfg.anonKey.includes("YOUR-");

const $ = (id) => document.getElementById(id);

const cloud = {
  enabled: CONFIGURED,
  user: null,
  client: null,
  _listeners: [],
  onChange(cb) { this._listeners.push(cb); },
  _emit() { this._listeners.forEach((cb) => cb(this.user)); },

  async saveGame(game) {
    if (!this.user) throw new Error("not signed in");
    const { error } = await this.client.from("games").insert(game);
    if (error) throw error;
  },
  async listGames() {
    if (!this.user) return [];
    const { data, error } = await this.client
      .from("games")
      .select("id, created_at, mode, opponent, white, black, result, termination, plies, pgn")
      .order("created_at", { ascending: false })
      .limit(50);
    if (error) throw error;
    return data || [];
  },
  async deleteGame(id) {
    const { error } = await this.client.from("games").delete().eq("id", id);
    if (error) throw error;
  },
};
window.DarwinCloud = cloud;

/* ----------------------------------------------------------------------- */
/* Auth panel UI                                                           */
/* ----------------------------------------------------------------------- */
function setAuthMsg(text, isError) {
  const m = $("authMsg");
  if (!m) return;
  m.textContent = text || "";
  m.classList.toggle("error", !!isError);
}

function renderAuth() {
  const signedOut = $("authSignedOut");
  const signedIn = $("authSignedIn");
  if (!signedOut || !signedIn) return;

  if (!cloud.enabled) {
    signedOut.classList.add("hidden");
    signedIn.classList.add("hidden");
    setAuthMsg("Sign-in not configured — fill web/supabase-config.js to save games.");
    return;
  }
  const user = cloud.user;
  signedOut.classList.toggle("hidden", !!user);
  signedIn.classList.toggle("hidden", !user);
  if (user) $("authWho").textContent = user.email || "signed in";
}

async function doSignUp() {
  const email = $("authEmail").value.trim();
  const password = $("authPassword").value;
  if (!email || !password) return setAuthMsg("Enter an email and password.", true);
  setAuthMsg("Creating account…");
  const { data, error } = await cloud.client.auth.signUp({ email, password });
  if (error) return setAuthMsg(error.message, true);
  setAuthMsg(data.session
    ? "Account created — you're signed in."
    : "Account created. Check your email to confirm, then sign in.");
}

async function doSignIn() {
  const email = $("authEmail").value.trim();
  const password = $("authPassword").value;
  if (!email || !password) return setAuthMsg("Enter an email and password.", true);
  setAuthMsg("Signing in…");
  const { error } = await cloud.client.auth.signInWithPassword({ email, password });
  if (error) return setAuthMsg(error.message, true);
  setAuthMsg("");
}

async function doGoogle() {
  setAuthMsg("Redirecting to Google…");
  const { error } = await cloud.client.auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo: window.location.origin + window.location.pathname },
  });
  if (error) {
    setAuthMsg(
      error.message.includes("provider is not enabled")
        ? "Google sign-in isn't enabled yet in Supabase (Auth → Providers → Google)."
        : error.message,
      true
    );
  }
}

async function doSignOut() {
  await cloud.client.auth.signOut();
  setAuthMsg("Signed out.");
}

async function init() {
  renderAuth();
  if (!cloud.enabled) return;

  let createClient;
  try {
    ({ createClient } = await import("https://esm.sh/@supabase/supabase-js@2"));
  } catch (err) {
    setAuthMsg("Couldn't load the auth library (offline?).", true);
    return;
  }
  cloud.client = createClient(cfg.url, cfg.anonKey);

  $("authGoogle").addEventListener("click", doGoogle);
  $("authSignUp").addEventListener("click", doSignUp);
  $("authSignIn").addEventListener("click", doSignIn);
  $("authSignOut").addEventListener("click", doSignOut);
  $("authPassword").addEventListener("keydown", (e) => { if (e.key === "Enter") doSignIn(); });

  cloud.client.auth.onAuthStateChange((_event, session) => {
    cloud.user = session ? session.user : null;
    renderAuth();
    cloud._emit();
  });
  const { data } = await cloud.client.auth.getSession();
  cloud.user = data.session ? data.session.user : null;
  renderAuth();
  cloud._emit();
}

init();
