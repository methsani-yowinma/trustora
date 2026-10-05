-- Trustora — Phase 2 foundation
-- profiles (1:1 with auth.users), roles, account status, audit log, RLS.
-- Apply on a Supabase project (auth schema, auth.uid(), anon/authenticated roles are provided by Supabase).

-- ---------------------------------------------------------------------------
-- Types
-- ---------------------------------------------------------------------------
create type public.user_role as enum ('CUSTOMER', 'SME', 'ADMIN');
create type public.account_status as enum ('ACTIVE', 'SUSPENDED');

-- ---------------------------------------------------------------------------
-- Shared helpers
-- ---------------------------------------------------------------------------
create function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- profiles
-- ---------------------------------------------------------------------------
create table public.profiles (
  id               uuid primary key references auth.users (id) on delete cascade,
  role             public.user_role not null default 'CUSTOMER',
  status           public.account_status not null default 'ACTIVE',
  full_name        text check (char_length(full_name) between 1 and 120),
  phone            text check (phone ~ '^\+?[0-9 ]{7,20}$'),
  -- Supported UI locales. Adding Tamil = extend this list in a new migration.
  preferred_locale text not null default 'en' check (preferred_locale in ('en', 'si')),
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create index profiles_role_idx on public.profiles (role);

create trigger profiles_set_updated_at
  before update on public.profiles
  for each row execute function public.set_updated_at();

-- Security-definer so RLS policies can check the caller's role without recursion.
create function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.profiles
    where id = auth.uid() and role = 'ADMIN' and status = 'ACTIVE'
  );
$$;

revoke all on function public.is_admin() from public, anon;
grant execute on function public.is_admin() to authenticated;

-- Create a profile for every new auth user.
-- Signup metadata is user-controlled: only CUSTOMER or SME may be requested, never ADMIN.
create function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  requested_role   text := new.raw_user_meta_data ->> 'role';
  requested_locale text := new.raw_user_meta_data ->> 'locale';
  requested_name   text := left(nullif(trim(new.raw_user_meta_data ->> 'full_name'), ''), 120);
begin
  insert into public.profiles (id, role, full_name, preferred_locale)
  values (
    new.id,
    case when requested_role = 'SME' then 'SME'::public.user_role else 'CUSTOMER'::public.user_role end,
    requested_name,
    case when requested_locale in ('en', 'si') then requested_locale else 'en' end
  );
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Only admins (or privileged backend/database roles) may change role or status.
create function public.protect_profile_privileges()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if (new.role is distinct from old.role or new.status is distinct from old.status)
     and current_user in ('anon', 'authenticated')
     and not public.is_admin() then
    raise exception 'Only administrators can change role or account status'
      using errcode = '42501';
  end if;
  return new;
end;
$$;

create trigger profiles_protect_privileges
  before update on public.profiles
  for each row execute function public.protect_profile_privileges();

alter table public.profiles enable row level security;

create policy profiles_select_own_or_admin on public.profiles
  for select to authenticated
  using (id = auth.uid() or public.is_admin());

create policy profiles_update_own_or_admin on public.profiles
  for update to authenticated
  using (id = auth.uid() or public.is_admin())
  with check (id = auth.uid() or public.is_admin());

-- No insert/delete policies: rows are created by the signup trigger and removed with auth.users.
revoke all on public.profiles from anon, authenticated;
grant select on public.profiles to authenticated;
grant update (full_name, phone, preferred_locale, role, status) on public.profiles to authenticated;

-- ---------------------------------------------------------------------------
-- audit_logs (append-only; written by the backend's privileged connection)
-- ---------------------------------------------------------------------------
create table public.audit_logs (
  id          bigint generated always as identity primary key,
  actor_id    uuid references public.profiles (id) on delete set null,
  actor_role  public.user_role,
  action      text not null check (action ~ '^[a-z_]+\.[a-z_]+$'),
  target_type text not null check (char_length(target_type) between 1 and 50),
  target_id   text,
  metadata    jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now()
);

create index audit_logs_created_at_idx on public.audit_logs (created_at desc);
create index audit_logs_actor_idx on public.audit_logs (actor_id);
create index audit_logs_target_idx on public.audit_logs (target_type, target_id);

create function public.prevent_audit_log_changes()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception 'audit_logs is append-only' using errcode = '42501';
end;
$$;

create trigger audit_logs_append_only
  before update or delete on public.audit_logs
  for each row execute function public.prevent_audit_log_changes();

alter table public.audit_logs enable row level security;

create policy audit_logs_select_admin on public.audit_logs
  for select to authenticated
  using (public.is_admin());

revoke all on public.audit_logs from anon, authenticated;
grant select on public.audit_logs to authenticated;
