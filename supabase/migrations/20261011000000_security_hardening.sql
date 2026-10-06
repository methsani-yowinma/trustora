-- Phase 9 — Security hardening.
--
-- 1. Domain tables are reachable only through the Trustora API.
--    Supabase exposes the `public` schema through its Data API (PostgREST/GraphQL) to the
--    `anon` and `authenticated` roles. Trustora never uses that path (the browser uses Supabase
--    for sign-in only), but the grants that let the backend run queries *as* those roles also
--    let any signed-in user query tables directly, where per-role column grants are wider than
--    what the API returns (e.g. reviews.customer_id, sme_social_accounts.verification_code).
--
--    A RESTRICTIVE policy on every table now requires the transaction-local setting
--    `trustora.api = 'on'`, which only the backend sets (app/core/db.py). Restrictive policies
--    are AND-ed with the existing permissive ones, so every existing rule still applies to API
--    requests, while direct Data API requests see no rows and cannot write. PostgREST only sets
--    its own `request.*` settings; clients cannot set arbitrary configuration parameters.
--
-- 2. RLS helper functions move to a `private` schema that the Data API does not expose, so they
--    can no longer be called as RPC endpoints. Policies and constraints reference functions by
--    OID and keep working; function bodies that call helpers by name are recreated below.

-- ---------------------------------------------------------------------------
-- 1. API-only access
-- ---------------------------------------------------------------------------
do $$
declare
  t record;
begin
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format(
      'create policy api_only on public.%I as restrictive for all to anon, authenticated '
      'using (current_setting(''trustora.api'', true) = ''on'') '
      'with check (current_setting(''trustora.api'', true) = ''on'')',
      t.tablename
    );
  end loop;
end;
$$;

-- ---------------------------------------------------------------------------
-- 2. Helper functions out of the exposed schema
-- ---------------------------------------------------------------------------
create schema private;
revoke all on schema private from public;
-- Policies evaluate the helpers with the caller's privileges, so the roles need USAGE.
grant usage on schema private to anon, authenticated;

alter function public.is_admin() set schema private;
alter function public.has_active_role(public.user_role) set schema private;
alter function public.owns_sme(uuid) set schema private;
alter function public.is_public_sme(uuid) set schema private;
alter function public.product_sme(uuid) set schema private;
alter function public.can_view_order(uuid) set schema private;
alter function public.can_view_complaint(uuid) set schema private;
alter function public.is_localized_text(jsonb, int) set schema private;

create or replace function private.can_view_order(target uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.orders o
    where o.id = target
      and (o.customer_id = auth.uid() or private.owns_sme(o.sme_id) or private.is_admin())
  );
$$;

create or replace function private.can_view_complaint(target uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.complaints c
    where c.id = target
      and (c.customer_id = auth.uid() or private.owns_sme(c.sme_id) or private.is_admin())
  );
$$;

create or replace function public.protect_profile_privileges()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if (new.role is distinct from old.role or new.status is distinct from old.status)
     and current_user in ('anon', 'authenticated')
     and not private.is_admin() then
    raise exception 'Only administrators can change role or account status'
      using errcode = '42501';
  end if;
  return new;
end;
$$;

create or replace function public.protect_sme_fields()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if current_user in ('anon', 'authenticated') and not private.is_admin() then
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

create or replace function public.protect_product_fields()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if current_user in ('anon', 'authenticated') and not private.is_admin() then
    if new.sme_id is distinct from old.sme_id
       or new.authenticity_status is distinct from old.authenticity_status then
      raise exception 'Only administrators can change product ownership or authenticity'
        using errcode = '42501';
    end if;
  end if;
  return new;
end;
$$;
