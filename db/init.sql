create table products (
  sku         text primary key,
  name        text not null,
  price_cents integer not null
);

create table orders (
  id           bigserial primary key,
  sku          text not null references products (sku),
  qty          integer not null,
  amount_cents integer not null,
  status       text not null,
  created_at   timestamptz not null default now()
);

insert into products values
  ('sku-1', 'Espresso beans 1kg', 2400),
  ('sku-2', 'Pour-over kettle', 5900),
  ('sku-3', 'Burr grinder', 12900),
  ('sku-4', 'Paper filters x100', 600);

-- Read-only user for the monitoring collector.
create user otel_monitor with password 'otel_monitor';
grant pg_monitor to otel_monitor;
