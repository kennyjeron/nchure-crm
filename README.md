# NCHURE CRM

NCHURE Client & Business Management CRM with a static HTML/Tailwind frontend and FastAPI/PostgreSQL backend.

## Stack
- Frontend: HTML, Tailwind CSS, Vanilla JavaScript, Chart.js
- Backend: FastAPI, Python, PostgreSQL/Supabase
- Hosting: Vercel

## Environment variables
Set these in Vercel:
- `DATABASE_URL` = Supabase PostgreSQL connection string
- `JWT_SECRET` = long random production secret

Never commit `.env` or database passwords.

## API
- `GET /health`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/state`
- CRUD: `/api/clients`, `/api/leads`, `/api/projects`, `/api/tasks`, `/api/invoices`, `/api/payments`, `/api/expenses`

## Initial accounts
- Founder: jero@nchure.com / jero123
- Founder: amar@nchure.com / amar123
- Admin: ashin@nchure.com / ashin123

Change these passwords after first production login.

## Vercel
Import this repository as a Vercel project. The included `vercel.json` routes `/api/*` to the FastAPI entrypoint and serves `index.html` for the frontend.

## Database
The API can create its core tables automatically on startup. For an existing Supabase CRM database, keep the existing schema and set `DATABASE_URL` to the project's pooled PostgreSQL connection string.
