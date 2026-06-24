/* Darwin's Gambit — Supabase browser config (Phase 5).
 *
 * Copy this file to `supabase-config.js` (same folder) and fill in your
 * project's two PUBLIC values from Supabase → Project Settings → API:
 *
 *   url      = Project URL            (e.g. https://abcd1234.supabase.co)
 *   anonKey  = Project API key "anon" / "publishable"
 *
 * These two are SAFE in the browser *because Row Level Security is enabled*
 * (see supabase/schema.sql). They identify the project and let the client
 * sign in; RLS is what actually protects the data.
 *
 * NEVER put the service-role / secret key here — it bypasses RLS and must stay
 * server-side only. `supabase-config.js` is gitignored so your values aren't
 * committed.
 */
window.SUPABASE_CONFIG = {
  url: "https://YOUR-PROJECT.supabase.co",
  anonKey: "YOUR-ANON-PUBLIC-KEY",
};
