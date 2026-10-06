-- Trustora — Phase 7: stored Gemini analyses.
-- AI output is *analysis*: it is labelled as such and never changes scores, verification or
-- complaint outcomes. Rows are written by the backend only and readable by admins only.

create type public.ai_analysis_kind as enum ('COMPLAINT', 'REVIEW', 'DOCUMENT', 'TRUST_EXPLANATION');
create type public.ai_analysis_status as enum ('DONE', 'FAILED', 'SKIPPED');

create table public.ai_analyses (
  id             uuid primary key default gen_random_uuid(),
  kind           public.ai_analysis_kind not null,
  -- complaint id, review id, evidence id, or sme id (trust explanations)
  target_id      uuid not null,
  sme_id         uuid not null references public.smes (id) on delete cascade,
  locale         text check (locale in ('en', 'si')),
  -- Hash of the exact input, so cached outputs are reused only for identical inputs.
  input_hash     char(64) check (input_hash ~ '^[0-9a-f]{64}$'),
  model          text not null check (char_length(model) between 1 and 80),
  prompt_version text not null check (char_length(prompt_version) between 1 and 40),
  status         public.ai_analysis_status not null,
  output         jsonb,
  error_code     text check (char_length(error_code) <= 60),
  created_at     timestamptz not null default now(),
  check ((status = 'DONE') = (output is not null))
);

create index ai_analyses_target_idx on public.ai_analyses (kind, target_id, created_at desc);
create index ai_analyses_sme_idx on public.ai_analyses (sme_id);
create unique index ai_analyses_explanation_cache
  on public.ai_analyses (target_id, locale, input_hash)
  where kind = 'TRUST_EXPLANATION' and status = 'DONE';

alter table public.ai_analyses enable row level security;

create policy ai_analyses_select_admin on public.ai_analyses
  for select to authenticated using (public.is_admin());

revoke all on public.ai_analyses from anon, authenticated;
grant select on public.ai_analyses to authenticated;
