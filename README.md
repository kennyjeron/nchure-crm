# NCHURE CRM

NCHURE CRM is a starter client, enquiry, project and operations dashboard.

## Stack
- Frontend: HTML, Tailwind CSS, Vanilla JavaScript, Chart.js
- API: FastAPI + Python
- Database: Supabase PostgreSQL
- Hosting configuration: Vercel (vercel.json)

## Important security notes
- Do not commit .env files, database URLs, passwords, or Supabase service-role keys.
- The API uses a server-side PostgreSQL connection string and a strong JWT_SECRET.
- No default login credentials are shipped. Configure the initial Founder account using hosting environment variables before first deployment.
- This is an MVP starter, not yet a complete multi-tenant production CRM. Add per-organization authorization, role-based permissions, rate limiting, and security tests before exposing it to real customer data.

## Supabase setup
A dedicated Supabase project has been created for NCHURE Lead Management. The application uses the namespaced tables crm_users, crm_clients, crm_leads, crm_projects, crm_tasks, crm_invoices, crm_payments, and crm_expenses. These are separate from the newer lead-management schema in the same project.

The database migration has been applied through Supabase. Use the PostgreSQL Transaction Pooler connection string from Supabase Connect where possible. Add it to the hosting provider as DATABASE_URL; never expose it in frontend code.

## Required hosting environment variables
- DATABASE_URL: Supabase PostgreSQL pooler connection string (server-side secret)
- JWT_SECRET: cryptographically random secret, at least 32 characters
- INITIAL_ADMIN_EMAIL: the first Founder account email
- INITIAL_ADMIN_PASSWORD: a unique password of at least 14 characters
- INITIAL_ADMIN_NAME: optional display name
- CORS_ORIGINS: optional comma-separated allowed origins (same-origin hosting does not need this)

On first startup, if the configured initial admin email does not exist, the API creates that Founder account. The password is hashed with PBKDF2. Remove INITIAL_ADMIN_PASSWORD from the hosting environment after the first successful initialization.

## Deploy
1. Import kennyjeron/nchure-crm into Vercel (or open the existing Vercel project linked to this repo).
2. Add the environment variables above in Vercel Project Settings -> Environment Variables for Production and Preview as appropriate.
3. Redeploy after setting variables.
4. Check /health. Confirm database_connected: true.
5. Test Founder login and CRUD using non-sensitive test records.

The repository's Vercel configuration routes /api/* and /health to api/index.py and serves index.html.

## Known limitations
The current UI is an early MVP. Tenant isolation and fine-grained permissions are not complete, so do not use it for confidential or real client data until these are implemented and tested.
