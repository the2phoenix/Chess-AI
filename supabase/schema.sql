-- Darwin's Gambit — Supabase schema (Phase 5: auth + storage)
-- ---------------------------------------------------------------------------
-- Run this once in your Supabase project: SQL Editor → New query → paste → Run.
-- It creates two tables (profiles, games) and Row Level Security so each user
-- can only ever see/touch their OWN rows. Supabase Auth owns `auth.users`.
-- ---------------------------------------------------------------------------

-- ============================ 1. PROFILES ==================================
-- One row per user, linked 1:1 to auth.users.
create table if not exists public.profiles (
  id         uuid primary key references auth.users (id) on delete cascade,
  username   text,
  created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

drop policy if exists "profiles: owner can read"   on public.profiles;
drop policy if exists "profiles: owner can insert" on public.profiles;
drop policy if exists "profiles: owner can update" on public.profiles;

create policy "profiles: owner can read"
  on public.profiles for select using (auth.uid() = id);
create policy "profiles: owner can insert"
  on public.profiles for insert with check (auth.uid() = id);
create policy "profiles: owner can update"
  on public.profiles for update using (auth.uid() = id);

-- Auto-create a profile row whenever a new user signs up.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, username)
  values (
    new.id,
    coalesce(new.raw_user_meta_data ->> 'username', split_part(new.email, '@', 1))
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ============================== 2. GAMES ===================================
-- Saved games (PGN + metadata), owned by the user who saved them. `mode`
-- matches the PGN Mode tag the engine writes (see chess_io/pgn.py).
create table if not exists public.games (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
  created_at  timestamptz not null default now(),
  mode        text not null check (mode in ('ai_vs_ai', 'vs_trained', 'vs_adaptive')),
  opponent    text,             -- difficulty-ladder rung (vs_trained), if any
  white       text,
  black       text,
  result      text,             -- '1-0' | '0-1' | '1/2-1/2'
  termination text,
  plies       integer,
  pgn         text not null
);

alter table public.games enable row level security;

drop policy if exists "games: owner can read"   on public.games;
drop policy if exists "games: owner can insert" on public.games;
drop policy if exists "games: owner can delete" on public.games;

create policy "games: owner can read"
  on public.games for select using (auth.uid() = user_id);
create policy "games: owner can insert"
  on public.games for insert with check (auth.uid() = user_id);
create policy "games: owner can delete"
  on public.games for delete using (auth.uid() = user_id);

create index if not exists games_user_created_idx
  on public.games (user_id, created_at desc);


-- Per-user adaptive opponent model (Mode F3). One row per user holds the
-- serialised OpponentModel (training/opponent_model/model.py:to_dict) as JSON:
-- move habits, recurring-mistake positions, games seen. The *base* engine is
-- never personalised (GSD §4) — only this per-user layer. Compute that reads/
-- writes it runs server-side (the local viewer, or the optional FastAPI
-- backend); the browser never runs the Python engine. RLS still scopes every
-- row to its owner.
create table if not exists public.opponent_models (
  user_id     uuid primary key default auth.uid() references auth.users (id) on delete cascade,
  updated_at  timestamptz not null default now(),
  games_seen  integer not null default 0,
  model       jsonb not null default '{}'::jsonb
);

alter table public.opponent_models enable row level security;

drop policy if exists "opponent_models: owner can read"   on public.opponent_models;
drop policy if exists "opponent_models: owner can upsert" on public.opponent_models;
drop policy if exists "opponent_models: owner can update" on public.opponent_models;

create policy "opponent_models: owner can read"
  on public.opponent_models for select using (auth.uid() = user_id);
create policy "opponent_models: owner can upsert"
  on public.opponent_models for insert with check (auth.uid() = user_id);
create policy "opponent_models: owner can update"
  on public.opponent_models for update using (auth.uid() = user_id);
