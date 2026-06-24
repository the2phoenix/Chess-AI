# Security Model — Darwin's Gambit

Two **separate** concerns. Don't conflate them — they need different fixes.

| Concern | Question | Fixed by |
|---|---|---|
| Access control | "Can someone reach another account by changing a link/id?" | Supabase Auth + Row-Level Security |
| Encryption | "Can stored data be read if leaked?" | HTTPS in transit + at-rest |

---

## 1. Access control — stops the "change the link" attack

**Stack:** Supabase Auth (login) + Supabase Postgres (data), enforced by **Row-Level Security (RLS)**.

**How it actually protects you:** the user logs in with Supabase Auth — email +
password, or Google OAuth — and the Supabase client carries that session's signed
JWT on every request. Supabase verifies it and exposes the user's id to the
database as `auth.uid()`. The RLS policies in `supabase/schema.sql` require each
row's `user_id` to equal `auth.uid()`. **The database itself refuses to return or
change rows that aren't yours** — so editing an id or URL in the browser does
nothing. Authorization is enforced at the database from a verified token, never
trusted from the client.

### Setup (already in the schema)
1. `supabase/schema.sql` creates the `profiles`, `games`, and `opponent_models`
   tables, **enables RLS on each**, and adds owner-scoped policies
   (`auth.uid() = user_id`).
2. A signup trigger auto-creates a `profiles` row for each new user.
3. Apply it once in the Supabase SQL editor; auth (email + Google) is toggled on
   in the Supabase dashboard.

### Golden rules
- **RLS is the real fix here — not encryption.** Encryption protects data
  confidentiality; it does nothing to stop unauthorized *access*.
- The **anon / publishable key** is safe in the browser **only with RLS enabled**
  (it's designed to be public; RLS is what makes that safe).
- The **service-role key** bypasses RLS — it's for an offline trainer/backend
  **only**, never the browser, never the repo.

---

## 2. Encryption — confidentiality of stored data

- **In transit:** HTTPS, automatic with Supabase. Nothing to do.
- **At rest:** Supabase/Postgres encrypts data at rest by default. Nothing to do.

For the data this app stores (games, profiles, evolution stats), **HTTPS +
at-rest + RLS is already strong**. Field-level client-side encryption would only
be worth adding for genuinely sensitive values, and the standard primitive there
is AES-GCM via the Web Crypto API with a fresh random IV per message — never a
homemade cipher, never a hardcoded key.

---

## TL;DR
- **Account safety →** Supabase Auth + RLS (this is what blocks the link/id attack).
- **Data confidentiality →** HTTPS + at-rest, both automatic.
- **Never** commit keys. Service-role key server-side only. Anon key safe only
  with RLS on. Real config lives in `web/supabase-config.js` (gitignored).
