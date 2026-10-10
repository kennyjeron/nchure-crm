-- CRM-compatible tables used by api/index.py.
-- Kept under crm_* names to avoid colliding with the lead-management schema.
create table if not exists public.crm_users (
 id bigserial primary key, name text not null, email text unique not null,
 password_hash text not null, role text not null check (role in ('Founder','CEO','Admin','CTO','COO','Team Leader','Staff','Client')),
 created_at timestamptz not null default now(), is_active boolean not null default true
);
create table if not exists public.crm_clients (
 id bigserial primary key, company text, contact text, email text, phone text,
 status text default 'Active', created_at timestamptz not null default now()
);
create table if not exists public.crm_leads (
 id bigserial primary key, name text, company text, contact text,
 status text default 'New', priority text default 'Medium',
 created_at timestamptz not null default now()
);
create table if not exists public.crm_projects (
 id bigserial primary key, name text, client_id bigint, status text default 'Planning',
 budget numeric not null default 0, created_at timestamptz not null default now()
);
create table if not exists public.crm_tasks (
 id bigserial primary key, title text, status text default 'Pending',
 priority text default 'Medium', due_date text, created_at timestamptz not null default now()
);
create table if not exists public.crm_invoices (
 id bigserial primary key, number text, client_id bigint, status text default 'Draft',
 total numeric not null default 0, created_at timestamptz not null default now()
);
create table if not exists public.crm_payments (
 id bigserial primary key, invoice_id bigint, amount numeric not null default 0,
 method text, created_at timestamptz not null default now()
);
create table if not exists public.crm_expenses (
 id bigserial primary key, title text, amount numeric not null default 0,
 category text, created_at timestamptz not null default now()
);
alter table public.crm_users enable row level security;
alter table public.crm_clients enable row level security;
alter table public.crm_leads enable row level security;
alter table public.crm_projects enable row level security;
alter table public.crm_tasks enable row level security;
alter table public.crm_invoices enable row level security;
alter table public.crm_payments enable row level security;
alter table public.crm_expenses enable row level security;
