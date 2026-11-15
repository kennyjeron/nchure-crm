# NCHURE CRM remediation runbook

Status date: 2026-11-15

## Safety boundary

- Production Supabase and Vercel have not been modified.
- Do not run migrations, restore projects, rotate secrets, change aliases, or redeploy production without explicit approval.
- Never print or copy secret values. Inspect only variable names and targets.

## Current verified state

- GitHub repository: kennyjeron/nchure-crm
- Base branch: main
- Repair branch: repair/phase-1-safe-db-foundation
- Production Vercel deployment is READY, but READY only confirms build/deployment state.
- Supabase project API reports status COMING_UP. Database table and migration queries currently fail with connection errors (including ECONNREFUSED).
- Live database schema, records, and migration history are therefore unverified.
- Existing migration creates crm_users, crm_clients, crm_leads, crm_projects, crm_tasks, crm_invoices, crm_payments, and crm_expenses.
- Existing migration does not create crm_dashboard_state, although api/index.py reads and writes it.
- Existing crm_users role check permits only eight roles; API TEAM_ROLES supports many additional roles.
- README claims automatic INITIAL_ADMIN_* bootstrap, but api/index.py explicitly says bootstrap is not run and contains no INITIAL_ADMIN_* references.

## Phase 1: database recovery (blocked)

1. Wait for Supabase project to reach ACTIVE.
2. Confirm project status and connection via Supabase tooling.
3. Take/verify a backup before schema changes.
4. Inspect live public tables, constraints, indexes, RLS policies, and migration history.
5. Compare live schema with repository migrations. Do not assume repository migrations were applied correctly.
6. Verify whether crm_dashboard_state exists and whether it contains records.
7. Only after review, apply the reviewed compatibility migration in a maintenance window.
8. Validate row counts and a non-destructive SELECT health check.

## Proposed migration

supabase/migrations/20261115_repair_workspace_state_and_roles.sql

This creates the missing workspace state table if absent, adds an optional FK to crm_users, and removes the obsolete eight-role constraint in favour of a non-empty role constraint. The API remains responsible for validating allowed role names.

This migration is NOT approved for production execution. Inspect existing schema and unexpected role values first.

## Backend work after database recovery

- Implement explicit, idempotent Founder bootstrap (or a one-time CLI/admin command), with no default credentials and no secret logging.
- Add server-side login throttling and account-aware abuse controls.
- Review token storage and XSS protections.
- Replace whole-workspace last-write-wins writes with versioned/transactional updates or normalized resource APIs.
- Add organization_id to all tenant-owned records and enforce tenant scoping at every query.
- Add automated tests for each role/resource combination.

## Release gates

- Supabase ACTIVE and verified backup.
- All migrations applied and schema inspected.
- /health reports database_connected=true.
- Founder login and role CRUD verified with test accounts.
- Cross-tenant access tests pass.
- Concurrent update and save-failure tests pass.
- Backup restore drill succeeds.
- Production deployment only after explicit owner approval.
