# NCHURE CRM

NCHURE CRM is an early client, enquiry, project and operations dashboard.

## Stack
- Frontend: HTML, Tailwind CSS, Vanilla JavaScript, Chart.js
- API: FastAPI + Python
- Database: Supabase PostgreSQL
- Hosting configuration: Vercel (vercel.json)

## Security and production status

- Never commit .env files, database URLs, passwords, JWT secrets, or Supabase service-role keys.
- The API uses a server-side PostgreSQL connection string and JWT_SECRET.
- This repository is an MVP, not a production-ready multi-tenant CRM.
- Organization-level isolation, server-side login throttling, granular permissions, backup/restore validation, and security tests are not complete.
- Do not use this deployment for confidential or real customer data until the release gates in docs/REMEDIATION_RUNBOOK.md pass.

## Supabase setup

The application expects these namespaced tables:
- crm_users
- crm_clients
- crm_leads
- crm_projects
- crm_tasks
- crm_invoices
- crm_payments
- crm_expenses
- crm_dashboard_state

The original base migration creates the first eight tables but does not create crm_dashboard_state. A proposed compatibility migration is available at supabase/migrations/20261115_repair_workspace_state_and_roles.sql. It has NOT been applied to the production database.

The Supabase project must be ACTIVE and its live schema must be inspected before any migration is applied. Take and verify a backup first. Use the PostgreSQL Transaction Pooler connection string from Supabase Connect where possible. Configure it as DATABASE_URL in the server hosting environment; never expose it in frontend code.

## Required hosting environment variables

- DATABASE_URL: Supabase PostgreSQL pooler connection string (server-side secret)
- JWT_SECRET: cryptographically random secret, at least 32 characters
- CORS_ORIGINS: optional comma-separated allowed origins

The current API code does NOT implement automatic INITIAL_ADMIN_* account bootstrap. The old setup instructions referring to INITIAL_ADMIN_EMAIL, INITIAL_ADMIN_PASSWORD and INITIAL_ADMIN_NAME were inaccurate. An existing Founder account must be provisioned through a separately reviewed, secure process before first login. Do not assume the presence of these environment variables creates an account.

## Deploy

1. Confirm the intended Vercel project and branch.
2. Configure DATABASE_URL and JWT_SECRET as server-only environment variables.
3. Confirm Supabase is ACTIVE and the schema matches the reviewed migrations.
4. Check /health and confirm database_connected: true.
5. Test Founder login and CRUD using non-sensitive test records.
6. Do not deploy to production until all release gates in docs/REMEDIATION_RUNBOOK.md pass and the owner explicitly approves.

The repository's Vercel configuration routes /api/* and /health to api/index.py and serves index.html.

## Known limitations

The current UI is an early MVP. The primary workspace is persisted as a JSONB snapshot and the browser currently participates in state caching/synchronization. Tenant isolation and fine-grained permissions are incomplete. The current frontend and API need automated tests, concurrency protection, server-side rate limiting, and a verified backup/restore process before production use.
