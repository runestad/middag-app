create table if not exists public.recipes (
  id text primary key,
  app_id text not null default 'oyvind-melanie',
  name text,
  category text,
  source text,
  link text,
  status text,
  data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists recipes_app_id_idx on public.recipes(app_id);
create index if not exists recipes_name_idx on public.recipes(name);
create index if not exists recipes_category_idx on public.recipes(category);

create table if not exists public.app_state (
  key text primary key,
  app_id text not null default 'oyvind-melanie',
  data jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create index if not exists app_state_app_id_idx on public.app_state(app_id);

create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists recipes_set_updated_at on public.recipes;
create trigger recipes_set_updated_at
before update on public.recipes
for each row execute function public.set_updated_at();

drop trigger if exists app_state_set_updated_at on public.app_state;
create trigger app_state_set_updated_at
before update on public.app_state
for each row execute function public.set_updated_at();

alter table public.recipes enable row level security;
alter table public.app_state enable row level security;
