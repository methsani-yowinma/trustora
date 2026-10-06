-- Trustora — Phase 4: Trust Engine storage (current scores, signals, history) and evidence review.
-- Scores are computed by the backend's deterministic trust engine; clients can only read them.

create type public.trust_level as enum ('VERIFIED', 'TRUSTED', 'DEVELOPING', 'CAUTION', 'HIGH_RISK');
create type public.trust_dimension as enum ('BUSINESS', 'PRODUCT', 'TRANSACTION');
create type public.trust_signal_kind as enum ('POSITIVE', 'RISK', 'INFO');

-- Admin review outcome: evidence rejected as *misleading* (e.g. forged or mismatched) is itself
-- a verified risk finding, unlike evidence that is merely insufficient or illegible.
alter table public.evidence
  add column flagged_misleading boolean not null default false,
  add constraint evidence_misleading_only_when_rejected
    check (not flagged_misleading or review_status = 'REJECTED');

grant update (flagged_misleading) on public.evidence to authenticated;

-- ---------------------------------------------------------------------------
-- Current score per SME (one row, replaced on every recalculation)
-- ---------------------------------------------------------------------------
create table public.trust_scores (
  sme_id            uuid primary key references public.smes (id) on delete cascade,
  overall_score     smallint not null check (overall_score between 0 and 100),
  level             public.trust_level not null,
  business_score    smallint not null check (business_score between 0 and 100),
  product_score     smallint not null check (product_score between 0 and 100),
  transaction_score smallint not null check (transaction_score between 0 and 100),
  rules_version     text not null,
  -- Aggregate counts only (by provenance/review state); evidence rows themselves stay private.
  evidence_summary  jsonb not null default '{}'::jsonb,
  computed_at       timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Current signals (the explanation behind the score). Replaced on every recalculation.
-- ---------------------------------------------------------------------------
create table public.trust_signals (
  id           bigint generated always as identity primary key,
  sme_id       uuid not null references public.smes (id) on delete cascade,
  dimension    public.trust_dimension not null,
  kind         public.trust_signal_kind not null,
  code         text not null check (code ~ '^[A-Z_]{3,60}$'),
  points       smallint not null,
  provenance   public.evidence_provenance not null,
  params       jsonb not null default '{}'::jsonb,
  evidence_ids uuid[] not null default '{}',
  created_at   timestamptz not null default now()
);

create index trust_signals_sme_idx on public.trust_signals (sme_id);

-- ---------------------------------------------------------------------------
-- History (append-only): one row whenever the score or level changes.
-- ---------------------------------------------------------------------------
create table public.trust_score_history (
  id                bigint generated always as identity primary key,
  sme_id            uuid not null references public.smes (id) on delete cascade,
  overall_score     smallint not null check (overall_score between 0 and 100),
  level             public.trust_level not null,
  business_score    smallint not null check (business_score between 0 and 100),
  product_score     smallint not null check (product_score between 0 and 100),
  transaction_score smallint not null check (transaction_score between 0 and 100),
  rules_version     text not null,
  trigger           text not null check (char_length(trigger) between 1 and 60),
  created_at        timestamptz not null default now()
);

create index trust_score_history_sme_idx on public.trust_score_history (sme_id, created_at desc);

create function public.prevent_trust_history_changes()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  -- Rows disappear only when their SME is deleted (cascade); history is never edited.
  if tg_op = 'UPDATE' then
    raise exception 'trust_score_history is append-only' using errcode = '42501';
  end if;
  if exists (select 1 from public.smes where id = old.sme_id) then
    raise exception 'trust_score_history is append-only' using errcode = '42501';
  end if;
  return old;
end;
$$;

create trigger trust_score_history_append_only
  before update or delete on public.trust_score_history
  for each row execute function public.prevent_trust_history_changes();

-- ---------------------------------------------------------------------------
-- RLS: public trust data for public stores; owners and admins see their own/all.
-- No client write grants at all — only the backend's trust engine writes.
-- ---------------------------------------------------------------------------
alter table public.trust_scores enable row level security;
alter table public.trust_signals enable row level security;
alter table public.trust_score_history enable row level security;

create policy trust_scores_select on public.trust_scores
  for select to anon, authenticated
  using (public.is_public_sme(sme_id) or public.owns_sme(sme_id) or public.is_admin());

create policy trust_signals_select on public.trust_signals
  for select to anon, authenticated
  using (public.is_public_sme(sme_id) or public.owns_sme(sme_id) or public.is_admin());

create policy trust_history_select on public.trust_score_history
  for select to anon, authenticated
  using (public.is_public_sme(sme_id) or public.owns_sme(sme_id) or public.is_admin());

revoke all on public.trust_scores, public.trust_signals, public.trust_score_history from anon, authenticated;
grant select on public.trust_scores, public.trust_signals, public.trust_score_history to anon, authenticated;

-- owns_sme/is_admin are called by anon policies too (they return false for anon).
grant execute on function public.owns_sme(uuid) to anon;
grant execute on function public.is_admin() to anon;
