-- Trustora — Phase 6: verified-purchase reviews, complaints (allegation → decision), complaint evidence.
-- All writes go through the backend. Complaint text is private to the parties and admins; the
-- public only ever sees aggregated categories and outcomes.

create type public.complaint_category as enum (
  'DELIVERY', 'WRONG_PRODUCT', 'PRODUCT_AUTHENTICITY', 'REFUND', 'PAYMENT',
  'CUSTOMER_SERVICE', 'PRODUCT_QUALITY', 'OTHER'
);
create type public.complaint_status as enum (
  'SUBMITTED', 'SME_RESPONDED', 'UNDER_REVIEW', 'RESOLVED', 'UPHELD', 'DISMISSED'
);

-- ---------------------------------------------------------------------------
-- reviews: one per delivered order ("verified buyer")
-- ---------------------------------------------------------------------------
create table public.reviews (
  id               uuid primary key default gen_random_uuid(),
  order_id         uuid not null unique references public.orders (id) on delete cascade,
  sme_id           uuid not null references public.smes (id) on delete cascade,
  customer_id      uuid not null references public.profiles (id) on delete cascade,
  rating           smallint not null check (rating between 1 and 5),
  comment          text check (char_length(comment) between 1 and 1000),
  sme_response     text check (char_length(sme_response) between 1 and 1000),
  sme_responded_at timestamptz,
  created_at       timestamptz not null default now()
);

create index reviews_sme_idx on public.reviews (sme_id, created_at desc);

alter table public.reviews enable row level security;

create policy reviews_select_public on public.reviews
  for select to anon, authenticated using (public.is_public_sme(sme_id));
create policy reviews_select_party on public.reviews
  for select to authenticated
  using (customer_id = auth.uid() or public.owns_sme(sme_id) or public.is_admin());

revoke all on public.reviews from anon, authenticated;
-- Reviewer identity is never public.
grant select (id, sme_id, rating, comment, sme_response, sme_responded_at, created_at)
  on public.reviews to anon;
grant select on public.reviews to authenticated;

-- ---------------------------------------------------------------------------
-- complaints: customer allegation → SME response → (escalation) → admin decision
-- ---------------------------------------------------------------------------
create table public.complaints (
  id               uuid primary key default gen_random_uuid(),
  order_id         uuid not null references public.orders (id) on delete cascade,
  sme_id           uuid not null references public.smes (id) on delete cascade,
  customer_id      uuid not null references public.profiles (id) on delete cascade,
  category         public.complaint_category not null,
  description      text not null check (char_length(description) between 10 and 2000),
  status           public.complaint_status not null default 'SUBMITTED',
  sme_response     text check (char_length(sme_response) between 1 and 2000),
  sme_responded_at timestamptz,
  escalated_at     timestamptz,
  resolution_note  text check (char_length(resolution_note) between 1 and 1000),
  decided_by       uuid references public.profiles (id) on delete set null,
  decided_at       timestamptz,
  closed_at        timestamptz,
  created_at       timestamptz not null default now(),
  check ((status in ('UPHELD', 'DISMISSED')) = (decided_at is not null)),
  check ((status in ('RESOLVED', 'UPHELD', 'DISMISSED')) = (closed_at is not null))
);

create index complaints_sme_idx on public.complaints (sme_id, status, created_at desc);
create index complaints_customer_idx on public.complaints (customer_id, created_at desc);
create index complaints_review_queue_idx on public.complaints (escalated_at) where status = 'UNDER_REVIEW';
-- At most one open complaint per order.
create unique index complaints_one_open_per_order on public.complaints (order_id)
  where status in ('SUBMITTED', 'SME_RESPONDED', 'UNDER_REVIEW');

create function public.can_view_complaint(target uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.complaints c
    where c.id = target
      and (c.customer_id = auth.uid() or public.owns_sme(c.sme_id) or public.is_admin())
  );
$$;

revoke all on function public.can_view_complaint(uuid) from public, anon;
grant execute on function public.can_view_complaint(uuid) to authenticated;

alter table public.complaints enable row level security;

create policy complaints_select_party on public.complaints
  for select to authenticated
  using (customer_id = auth.uid() or public.owns_sme(sme_id) or public.is_admin());

revoke all on public.complaints from anon, authenticated;
grant select on public.complaints to authenticated;

-- ---------------------------------------------------------------------------
-- Complaint evidence: both parties (and admins) can see evidence attached to the complaint.
-- ---------------------------------------------------------------------------
alter table public.evidence
  add column complaint_id uuid references public.complaints (id) on delete cascade;

create index evidence_complaint_idx on public.evidence (complaint_id) where complaint_id is not null;

create policy evidence_select_complaint_party on public.evidence
  for select to authenticated
  using (complaint_id is not null and public.can_view_complaint(complaint_id));
