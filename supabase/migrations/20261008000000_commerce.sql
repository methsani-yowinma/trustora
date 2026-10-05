-- Trustora — Phase 5: orders, order items, payments (sandbox), deliveries (provider abstraction).
-- All writes go through the backend (validated prices, stock, state machine); clients only read
-- the orders they are a party to.

create type public.order_status as enum (
  'PLACED', 'CONFIRMED', 'DISPATCHED', 'DELIVERED', 'COMPLETED', 'CANCELLED', 'DELIVERY_FAILED'
);
create type public.payment_method as enum ('COD', 'MOCK_CARD');
create type public.payment_status as enum ('PENDING', 'PAID', 'REFUNDED');
create type public.delivery_status as enum ('PENDING', 'DISPATCHED', 'IN_TRANSIT', 'DELIVERED', 'FAILED');

-- ---------------------------------------------------------------------------
-- orders (one SME per order)
-- ---------------------------------------------------------------------------
create table public.orders (
  id                  uuid primary key default gen_random_uuid(),
  order_number        text not null unique check (order_number ~ '^TR-[A-Z0-9]{8}$'),
  customer_id         uuid not null references public.profiles (id) on delete restrict,
  sme_id              uuid not null references public.smes (id) on delete restrict,
  status              public.order_status not null default 'PLACED',
  subtotal_lkr        numeric(12, 2) not null check (subtotal_lkr > 0),
  delivery_fee_lkr    numeric(12, 2) not null check (delivery_fee_lkr >= 0),
  total_lkr           numeric(12, 2) not null,
  -- Snapshot at checkout: {recipient_name, phone, address_line1, address_line2?, city, district, postal_code?}
  shipping_address    jsonb not null check (jsonb_typeof(shipping_address) = 'object'),
  payment_method      public.payment_method not null,
  idempotency_key     uuid not null,
  placed_at           timestamptz not null default now(),
  confirmed_at        timestamptz,
  dispatched_at       timestamptz,
  delivered_at        timestamptz,
  completed_at        timestamptz,
  cancelled_at        timestamptz,
  cancelled_by        public.user_role,
  cancellation_reason text check (char_length(cancellation_reason) <= 500),
  updated_at          timestamptz not null default now(),
  check (total_lkr = subtotal_lkr + delivery_fee_lkr),
  check ((status = 'CANCELLED') = (cancelled_at is not null and cancelled_by is not null)),
  unique (customer_id, idempotency_key)
);

create index orders_customer_idx on public.orders (customer_id, placed_at desc);
create index orders_sme_status_idx on public.orders (sme_id, status, placed_at desc);

create trigger orders_set_updated_at
  before update on public.orders
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- order_items (price and name snapshots)
-- ---------------------------------------------------------------------------
create table public.order_items (
  id                uuid primary key default gen_random_uuid(),
  order_id          uuid not null references public.orders (id) on delete cascade,
  product_id        uuid not null references public.products (id) on delete restrict,
  product_name_i18n jsonb not null check (public.is_localized_text(product_name_i18n, 160)),
  unit_price_lkr    numeric(12, 2) not null check (unit_price_lkr > 0),
  quantity          smallint not null check (quantity between 1 and 10),
  line_total_lkr    numeric(12, 2) not null,
  check (line_total_lkr = unit_price_lkr * quantity),
  unique (order_id, product_id)
);

create index order_items_order_idx on public.order_items (order_id);
create index order_items_product_idx on public.order_items (product_id);

-- ---------------------------------------------------------------------------
-- payments (sandbox: no real payment processing, no card data stored)
-- ---------------------------------------------------------------------------
create table public.payments (
  id             uuid primary key default gen_random_uuid(),
  order_id       uuid not null unique references public.orders (id) on delete cascade,
  method         public.payment_method not null,
  status         public.payment_status not null default 'PENDING',
  amount_lkr     numeric(12, 2) not null check (amount_lkr > 0),
  mock_reference text check (mock_reference ~ '^MOCK-[A-Z0-9]{10}$'),
  paid_at        timestamptz,
  refunded_at    timestamptz,
  created_at     timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- deliveries (provider abstraction; MVP provider is simulated)
-- ---------------------------------------------------------------------------
create table public.deliveries (
  id                      uuid primary key default gen_random_uuid(),
  order_id                uuid not null unique references public.orders (id) on delete cascade,
  provider_code           text not null check (provider_code ~ '^[A-Z_]{2,30}$'),
  district                text not null check (district ~ '^[A-Z_]{3,20}$'),
  fee_lkr                 numeric(12, 2) not null check (fee_lkr >= 0),
  eta_days                smallint not null check (eta_days between 1 and 30),
  status                  public.delivery_status not null default 'PENDING',
  tracking_ref            text unique check (tracking_ref ~ '^[A-Z0-9-]{6,40}$'),
  estimated_delivery_date date,
  dispatched_at           timestamptz,
  in_transit_at           timestamptz,
  delivered_at            timestamptz,
  failed_at               timestamptz,
  failure_reason          text check (char_length(failure_reason) <= 500)
);

create index deliveries_status_idx on public.deliveries (status);

-- ---------------------------------------------------------------------------
-- RLS: customers see their own orders; SMEs see orders placed with them; admins see all.
-- ---------------------------------------------------------------------------
create function public.can_view_order(target uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.orders o
    where o.id = target
      and (o.customer_id = auth.uid() or public.owns_sme(o.sme_id) or public.is_admin())
  );
$$;

revoke all on function public.can_view_order(uuid) from public, anon;
grant execute on function public.can_view_order(uuid) to authenticated;

alter table public.orders enable row level security;
alter table public.order_items enable row level security;
alter table public.payments enable row level security;
alter table public.deliveries enable row level security;

create policy orders_select_party on public.orders
  for select to authenticated
  using (customer_id = auth.uid() or public.owns_sme(sme_id) or public.is_admin());

create policy order_items_select_party on public.order_items
  for select to authenticated using (public.can_view_order(order_id));

create policy payments_select_party on public.payments
  for select to authenticated using (public.can_view_order(order_id));

create policy deliveries_select_party on public.deliveries
  for select to authenticated using (public.can_view_order(order_id));

revoke all on public.orders, public.order_items, public.payments, public.deliveries from anon, authenticated;
grant select on public.orders, public.order_items, public.payments, public.deliveries to authenticated;
