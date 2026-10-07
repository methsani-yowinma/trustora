-- Trustora — Phase 3: SMEs, storefronts, social accounts, verification, evidence, products.

-- ---------------------------------------------------------------------------
-- Types
-- ---------------------------------------------------------------------------
create type public.sme_status as enum ('ACTIVE', 'SUSPENDED');
create type public.verification_status as enum ('UNVERIFIED', 'PENDING', 'VERIFIED', 'REJECTED');
create type public.verification_decision as enum ('SUBMITTED', 'APPROVED', 'REJECTED');
create type public.social_platform as enum ('INSTAGRAM', 'FACEBOOK', 'TIKTOK', 'WHATSAPP');
create type public.product_status as enum ('ACTIVE', 'HIDDEN', 'REMOVED');
create type public.authenticity_status as enum ('VERIFIED', 'PARTIALLY_VERIFIED', 'UNVERIFIED', 'CONCERN');
create type public.evidence_type as enum (
  'BUSINESS_DOCUMENT', 'SOCIAL_CONTENT', 'CUSTOMER_REVIEW', 'CUSTOMER_COMPLAINT',
  'PRODUCT_DOCUMENT', 'PRODUCT_IMAGE', 'TRANSACTION_DATA', 'DELIVERY_DATA',
  'SELLER_CLAIM', 'VERIFICATION_RESULT'
);
create type public.evidence_provenance as enum (
  'VERIFIED_FACT', 'SELLER_CLAIM', 'CUSTOMER_ALLEGATION', 'PUBLIC_EVIDENCE',
  'AI_ANALYSIS', 'PLATFORM_STATISTIC'
);
create type public.evidence_review_status as enum ('PENDING', 'ACCEPTED', 'REJECTED');
create type public.evidence_availability as enum ('AVAILABLE', 'PREVIOUSLY_OBSERVED');

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------

-- Localized text: a JSON object whose keys are supported locales, values non-empty strings,
-- with at least one locale present. Adding Tamil = extend the key list in a new migration.
create function public.is_localized_text(value jsonb, max_length int)
returns boolean
language sql
immutable
set search_path = ''
as $$
  select jsonb_typeof(value) = 'object'
     and value <> '{}'::jsonb
     and not exists (
       select 1 from jsonb_each(value) as e(k, v)
       where e.k not in ('en', 'si')
          or jsonb_typeof(e.v) <> 'string'
          or char_length(e.v #>> '{}') not between 1 and max_length
     );
$$;

create function public.has_active_role(required public.user_role)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.profiles
    where id = auth.uid() and role = required and status = 'ACTIVE'
  );
$$;

-- ---------------------------------------------------------------------------
-- smes (one per SME account; includes storefront fields)
-- ---------------------------------------------------------------------------
create table public.smes (
  id                  uuid primary key default gen_random_uuid(),
  owner_id            uuid not null unique references public.profiles (id) on delete restrict,
  slug                text not null unique check (slug ~ '^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$'),
  name                text not null check (char_length(name) between 2 and 120),
  logo_path           text,
  description_i18n    jsonb check (description_i18n is null or public.is_localized_text(description_i18n, 2000)),
  -- {"returns": {"en": "...", "si": "..."}, "refunds": {...}, "delivery": {...}}
  policies_i18n       jsonb not null default '{}'::jsonb check (jsonb_typeof(policies_i18n) = 'object'),
  contact_email       text check (contact_email ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  contact_phone       text check (contact_phone ~ '^\+?[0-9 ]{7,20}$'),
  contact_verified    boolean not null default false,
  verification_status public.verification_status not null default 'UNVERIFIED',
  verified_at         timestamptz,
  is_published        boolean not null default false,
  status              public.sme_status not null default 'ACTIVE',
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

create index smes_public_idx on public.smes (is_published, status);

create trigger smes_set_updated_at
  before update on public.smes
  for each row execute function public.set_updated_at();

create function public.owns_sme(target uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (select 1 from public.smes where id = target and owner_id = auth.uid());
$$;

create function public.is_public_sme(target uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.smes where id = target and is_published and status = 'ACTIVE'
  );
$$;

-- Owners may edit their storefront but never their trust/verification fields.
-- Changing contact details after verification clears contact_verified.
create function public.protect_sme_fields()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if current_user in ('anon', 'authenticated') and not public.is_admin() then
    if new.owner_id is distinct from old.owner_id
       or new.slug is distinct from old.slug
       or new.logo_path is distinct from old.logo_path
       or new.verification_status is distinct from old.verification_status
       or new.verified_at is distinct from old.verified_at
       or new.status is distinct from old.status
       or (new.contact_verified and not old.contact_verified) then
      raise exception 'Only administrators can change verification or account fields'
        using errcode = '42501';
    end if;
  end if;

  if new.contact_email is distinct from old.contact_email
     or new.contact_phone is distinct from old.contact_phone then
    new.contact_verified := false;
  end if;
  return new;
end;
$$;

create trigger smes_protect_fields
  before update on public.smes
  for each row execute function public.protect_sme_fields();

alter table public.smes enable row level security;

create policy smes_select_public on public.smes
  for select to anon, authenticated
  using (is_published and status = 'ACTIVE');

create policy smes_select_own_or_admin on public.smes
  for select to authenticated
  using (owner_id = auth.uid() or public.is_admin());

create policy smes_insert_own on public.smes
  for insert to authenticated
  with check (owner_id = auth.uid() and public.has_active_role('SME'));

create policy smes_update_own_or_admin on public.smes
  for update to authenticated
  using (owner_id = auth.uid() or public.is_admin())
  with check (owner_id = auth.uid() or public.is_admin());

revoke all on public.smes from anon, authenticated;
grant select (id, slug, name, logo_path, description_i18n, policies_i18n, contact_email,
              contact_phone, contact_verified, verification_status, verified_at, is_published,
              status, created_at)
  on public.smes to anon;
grant select on public.smes to authenticated;
grant insert (owner_id, slug, name, description_i18n, policies_i18n, contact_email, contact_phone)
  on public.smes to authenticated;
grant update (name, description_i18n, policies_i18n, contact_email, contact_phone, is_published,
              contact_verified, verification_status, verified_at, status)
  on public.smes to authenticated;

-- ---------------------------------------------------------------------------
-- sme_social_accounts
-- ---------------------------------------------------------------------------
create table public.sme_social_accounts (
  id                 uuid primary key default gen_random_uuid(),
  sme_id             uuid not null references public.smes (id) on delete cascade,
  platform           public.social_platform not null,
  handle             text not null check (handle ~ '^[A-Za-z0-9_.+ -]{2,60}$'),
  -- Postgres regex repetition counts are capped at 255, so length is checked separately.
  url                text check (char_length(url) <= 300 and url ~ '^https://[^[:space:]]{4,}$'),
  -- Placed by the SME in their bio/about text; checked manually by an admin. Not a secret.
  verification_code  text not null unique check (verification_code ~ '^TRUSTORA-[A-Z0-9]{6}$'),
  ownership_verified boolean not null default false,
  verified_at        timestamptz,
  verified_by        uuid references public.profiles (id) on delete set null,
  created_at         timestamptz not null default now(),
  unique (sme_id, platform, handle)
);

create index sme_social_accounts_sme_idx on public.sme_social_accounts (sme_id);
create index sme_social_accounts_pending_idx on public.sme_social_accounts (created_at)
  where not ownership_verified;

alter table public.sme_social_accounts enable row level security;

create policy social_select_public on public.sme_social_accounts
  for select to anon, authenticated
  using (ownership_verified and public.is_public_sme(sme_id));

create policy social_select_own_or_admin on public.sme_social_accounts
  for select to authenticated
  using (public.owns_sme(sme_id) or public.is_admin());

create policy social_delete_own on public.sme_social_accounts
  for delete to authenticated
  using (public.owns_sme(sme_id));

create policy social_update_admin on public.sme_social_accounts
  for update to authenticated
  using (public.is_admin())
  with check (public.is_admin());

revoke all on public.sme_social_accounts from anon, authenticated;
grant select (id, sme_id, platform, handle, url, ownership_verified, verified_at)
  on public.sme_social_accounts to anon;
grant select, delete on public.sme_social_accounts to authenticated;
grant update (ownership_verified, verified_at, verified_by) on public.sme_social_accounts to authenticated;
-- Inserts are performed by the backend (generated verification codes).

-- ---------------------------------------------------------------------------
-- business_verifications
-- ---------------------------------------------------------------------------
create table public.business_verifications (
  id                   uuid primary key default gen_random_uuid(),
  sme_id               uuid not null references public.smes (id) on delete cascade,
  status               public.verification_decision not null default 'SUBMITTED',
  business_reg_number  text not null check (business_reg_number ~ '^[A-Za-z0-9/ -]{3,40}$'),
  registered_name      text not null check (char_length(registered_name) between 2 and 160),
  submitted_by         uuid references public.profiles (id) on delete set null,
  submitted_at         timestamptz not null default now(),
  reviewed_by          uuid references public.profiles (id) on delete set null,
  reviewed_at          timestamptz,
  decision_note        text check (char_length(decision_note) <= 1000),
  check ((status = 'SUBMITTED') = (reviewed_at is null))
);

create index business_verifications_sme_idx on public.business_verifications (sme_id, submitted_at desc);
create index business_verifications_queue_idx on public.business_verifications (submitted_at)
  where status = 'SUBMITTED';
-- At most one open application per SME.
create unique index business_verifications_one_open
  on public.business_verifications (sme_id) where status = 'SUBMITTED';

alter table public.business_verifications enable row level security;

create policy verifications_select_own_or_admin on public.business_verifications
  for select to authenticated
  using (public.owns_sme(sme_id) or public.is_admin());

create policy verifications_update_admin on public.business_verifications
  for update to authenticated
  using (public.is_admin())
  with check (public.is_admin());

revoke all on public.business_verifications from anon, authenticated;
grant select on public.business_verifications to authenticated;
grant update (status, reviewed_by, reviewed_at, decision_note)
  on public.business_verifications to authenticated;

-- ---------------------------------------------------------------------------
-- categories (reference data)
-- ---------------------------------------------------------------------------
create table public.categories (
  id         smallint generated always as identity primary key,
  slug       text not null unique check (slug ~ '^[a-z0-9-]{2,40}$'),
  name_i18n  jsonb not null check (public.is_localized_text(name_i18n, 80)),
  sort_order smallint not null default 0
);

alter table public.categories enable row level security;
create policy categories_select_all on public.categories for select to anon, authenticated using (true);
revoke all on public.categories from anon, authenticated;
grant select on public.categories to anon, authenticated;

insert into public.categories (slug, name_i18n, sort_order) values
  ('fashion',     '{"en": "Fashion & Clothing", "si": "විලාසිතා සහ ඇඳුම්"}', 1),
  ('beauty',      '{"en": "Beauty & Cosmetics", "si": "රූපලාවණ්‍ය සහ අලංකාර ද්‍රව්‍ය"}', 2),
  ('electronics', '{"en": "Electronics & Accessories", "si": "ඉලෙක්ට්‍රොනික සහ උපාංග"}', 3),
  ('home',        '{"en": "Home & Living", "si": "නිවස සහ ජීවන අවශ්‍යතා"}', 4),
  ('food',        '{"en": "Food & Groceries", "si": "ආහාර සහ සිල්ලර බඩු"}', 5),
  ('handicrafts', '{"en": "Handicrafts & Gifts", "si": "අත්කම් සහ තෑගි"}', 6),
  ('health',      '{"en": "Health & Wellness", "si": "සෞඛ්‍ය සහ යහපැවැත්ම"}', 7),
  ('kids',        '{"en": "Kids & Baby", "si": "ළමා සහ බිළිඳු"}', 8),
  ('other',       '{"en": "Other", "si": "වෙනත්"}', 99);

-- ---------------------------------------------------------------------------
-- products
-- ---------------------------------------------------------------------------
create table public.products (
  id                  uuid primary key default gen_random_uuid(),
  sme_id              uuid not null references public.smes (id) on delete cascade,
  category_id         smallint not null references public.categories (id),
  name_i18n           jsonb not null check (public.is_localized_text(name_i18n, 160)),
  description_i18n    jsonb check (description_i18n is null or public.is_localized_text(description_i18n, 5000)),
  price_lkr           numeric(12, 2) not null check (price_lkr > 0 and price_lkr <= 10000000),
  stock               integer not null default 0 check (stock between 0 and 1000000),
  status              public.product_status not null default 'ACTIVE',
  -- Set only from admin-reviewed evidence (Phase 4). Never from AI image judgement.
  authenticity_status public.authenticity_status not null default 'UNVERIFIED',
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

create index products_sme_status_idx on public.products (sme_id, status);
create index products_category_idx on public.products (category_id) where status = 'ACTIVE';

create trigger products_set_updated_at
  before update on public.products
  for each row execute function public.set_updated_at();

create function public.protect_product_fields()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if current_user in ('anon', 'authenticated') and not public.is_admin() then
    if new.sme_id is distinct from old.sme_id
       or new.authenticity_status is distinct from old.authenticity_status then
      raise exception 'Only administrators can change product ownership or authenticity'
        using errcode = '42501';
    end if;
  end if;
  return new;
end;
$$;

create trigger products_protect_fields
  before update on public.products
  for each row execute function public.protect_product_fields();

alter table public.products enable row level security;

create policy products_select_public on public.products
  for select to anon, authenticated
  using (status = 'ACTIVE' and public.is_public_sme(sme_id));

create policy products_select_own_or_admin on public.products
  for select to authenticated
  using (public.owns_sme(sme_id) or public.is_admin());

create policy products_insert_own on public.products
  for insert to authenticated
  with check (public.owns_sme(sme_id) and public.has_active_role('SME') and authenticity_status = 'UNVERIFIED');

create policy products_update_own_or_admin on public.products
  for update to authenticated
  using (public.owns_sme(sme_id) or public.is_admin())
  with check (public.owns_sme(sme_id) or public.is_admin());

revoke all on public.products from anon, authenticated;
grant select on public.products to anon, authenticated;
grant insert (sme_id, category_id, name_i18n, description_i18n, price_lkr, stock, status)
  on public.products to authenticated;
grant update (category_id, name_i18n, description_i18n, price_lkr, stock, status, authenticity_status)
  on public.products to authenticated;

-- ---------------------------------------------------------------------------
-- product_images (files in the public-media bucket; rows written by the backend)
-- ---------------------------------------------------------------------------
create table public.product_images (
  id           uuid primary key default gen_random_uuid(),
  product_id   uuid not null references public.products (id) on delete cascade,
  storage_path text not null unique,
  sha256       char(64) not null check (sha256 ~ '^[0-9a-f]{64}$'),
  sort_order   smallint not null default 0,
  created_at   timestamptz not null default now()
);

create index product_images_product_idx on public.product_images (product_id, sort_order);

create function public.product_sme(target uuid)
returns uuid
language sql
stable
security definer
set search_path = ''
as $$
  select sme_id from public.products where id = target;
$$;

alter table public.product_images enable row level security;

create policy product_images_select_public on public.product_images
  for select to anon, authenticated
  using (exists (
    select 1 from public.products p
    where p.id = product_id and p.status = 'ACTIVE' and public.is_public_sme(p.sme_id)
  ));

create policy product_images_select_own_or_admin on public.product_images
  for select to authenticated
  using (public.owns_sme(public.product_sme(product_id)) or public.is_admin());

revoke all on public.product_images from anon, authenticated;
grant select on public.product_images to anon, authenticated;

-- ---------------------------------------------------------------------------
-- evidence (written only by the backend; integrity-hashed)
-- ---------------------------------------------------------------------------
create table public.evidence (
  id              uuid primary key default gen_random_uuid(),
  type            public.evidence_type not null,
  provenance      public.evidence_provenance not null,
  sme_id          uuid not null references public.smes (id) on delete cascade,
  product_id      uuid references public.products (id) on delete cascade,
  verification_id uuid references public.business_verifications (id) on delete cascade,
  description     text check (char_length(description) <= 1000),
  source          text not null check (char_length(source) between 1 and 60),
  source_url      text check (source_url ~ '^https://'),
  storage_path    text unique,
  mime_type       text,
  size_bytes      integer check (size_bytes > 0),
  sha256          char(64) check (sha256 ~ '^[0-9a-f]{64}$'),
  observed_at     timestamptz not null default now(),
  availability    public.evidence_availability not null default 'AVAILABLE',
  review_status   public.evidence_review_status not null default 'PENDING',
  reviewed_by     uuid references public.profiles (id) on delete set null,
  reviewed_at     timestamptz,
  review_note     text check (char_length(review_note) <= 1000),
  created_by      uuid references public.profiles (id) on delete set null,
  created_at      timestamptz not null default now(),
  -- Stored files must carry an integrity hash.
  check (storage_path is null or (sha256 is not null and mime_type is not null and size_bytes is not null))
);

create index evidence_sme_idx on public.evidence (sme_id, created_at desc);
create index evidence_product_idx on public.evidence (product_id) where product_id is not null;
create index evidence_verification_idx on public.evidence (verification_id) where verification_id is not null;
create index evidence_review_queue_idx on public.evidence (created_at) where review_status = 'PENDING';

alter table public.evidence enable row level security;

create policy evidence_select_own_or_admin on public.evidence
  for select to authenticated
  using (public.owns_sme(sme_id) or public.is_admin());

create policy evidence_update_admin on public.evidence
  for update to authenticated
  using (public.is_admin())
  with check (public.is_admin());

revoke all on public.evidence from anon, authenticated;
grant select on public.evidence to authenticated;
grant update (review_status, reviewed_by, reviewed_at, review_note, availability)
  on public.evidence to authenticated;

-- ---------------------------------------------------------------------------
-- Storage buckets. No client policies on storage.objects: all uploads go through the
-- backend (validated, hashed). public-media is world-readable by URL; private-evidence is
-- served only through short-lived signed URLs issued by the backend.
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  ('public-media', 'public-media', true, 5242880, array['image/jpeg', 'image/png', 'image/webp']),
  ('private-evidence', 'private-evidence', false, 10485760,
   array['image/jpeg', 'image/png', 'image/webp', 'application/pdf'])
on conflict (id) do nothing;
