# NCHURE CRM — Firebase Spark migration preparation

**Branch:** `migration/firebase-spark`  
**Base:** `main`  
**Scope:** Firebase Hosting + Firebase Authentication (email/password) + Cloud Firestore on Spark only.

## Status

This branch is a migration foundation, **not a live cutover**.

- [x] Inspect current GitHub, Vercel and Supabase configuration read-only.
- [x] Create an isolated migration branch from `main`.
- [x] Add a deny-by-default Firestore Security Rules baseline.
- [x] Add the target Firestore schema and indexes.
- [x] Add pinned modular Firebase Web SDK bootstrap and a config template.
- [ ] Implement the UI data adapter and remove calls to the FastAPI `/api/*` endpoints.
- [ ] Add automated Firestore Rules tests and run them in the Emulator Suite.
- [ ] Test role-based flows with Founder, team member and Client accounts.
- [ ] Export and preserve local browser data; test import.
- [ ] Create Firebase project and configure Authentication + Firestore.
- [ ] Deploy a preview to Firebase Hosting and verify all CRM workflows.
- [ ] Approve production cutover separately.

**Do not run `firebase deploy` from this branch yet.** The unchanged `index.html`
still calls the existing FastAPI API. Deploying the current HTML to static Hosting
before the adapter is complete would break login and cloud sync.

## What the current app requires

The current repository is a static HTML/Tailwind/Vanilla JS dashboard, with a
FastAPI backend in `api/index.py` and PostgreSQL in Supabase. The UI calls
`/api/auth/login`, `/api/auth/me`, `/api/auth/change-password`,
`/api/team-members`, `/api/app-state`, client portal endpoints and CRUD routes.
The target Spark architecture has **no trusted Python server**, so those endpoints
must be replaced by Firebase client SDK calls and Firestore Rules.

The current Supabase project returned 17 public tables with zero rows. It also
returned zero rows in `auth.users`, `storage.objects` and `storage.buckets`.
The Vercel project currently contains server-side environment variables, but none
of them are copied into this branch. Do not copy any Vercel secrets to Firebase
Hosting or the browser.

## Spark-only service boundaries

Allowed in this plan:
- Firebase Hosting static site.
- Firebase Authentication with Email/Password (not phone/SMS auth).
- Cloud Firestore within Spark free quotas.
- Firebase Web SDK running in the browser.
- Firestore Security Rules for access control.

Excluded:
- Cloud Functions (requires Blaze).
- Cloud Run, Cloud SQL, App Hosting or any other billed Google Cloud service.
- Firebase phone/SMS authentication.
- Firebase Storage in the initial migration.
- Admin SDK credentials or service-account JSON in browser code.

Spark has no automatic pay-as-you-go overage. When a quota for a metered product
is exceeded, that product can stop serving until the quota resets or the project
is upgraded. Current published Firestore free quota: 1 GiB stored data, 50,000
document reads/day, 20,000 writes/day, 20,000 deletes/day and 10 GiB outbound
transfer/month. Hosting includes up to 10 GB stored content and up to 360 MB/day
data transfer on Spark. Exceeding a Spark quota stops that product until quota resets or the project is upgraded. Monitor usage rather than assuming unlimited free usage.

## One-time Firebase Console setup

Do this only after the UI adapter and Rules tests are ready.

1. Create a new Firebase project. Keep it on **Spark** and do not attach a billing account.
2. Add a Web App and copy its public web config into a local copy of
   `js/firebase-config.example.js` named `js/firebase-config.js`.
3. In Authentication, enable Email/Password. Do not enable Phone Authentication.
4. Create one Firestore Native mode database. Choose the nearest supported region
   deliberately; the Firestore location cannot be changed after creation.
5. Publish `firebase/firestore.rules` and `firebase/firestore.indexes.json` only
   after Rules tests pass.
6. Create the first Founder identity in Firebase Authentication, then create
   `organizations/nchure/users/{AUTH_UID}` in Firestore Console with
   `role: "Founder"` and `active: true`. Console-created documents use trusted
   project-admin permissions. Never implement public self-registration as Founder.
7. Team and Client accounts must be provisioned through the approved manager flow.
   The rules prevent a user from changing their own role.

## Local files and config

- Copy `js/firebase-config.example.js` to `js/firebase-config.js`.
- Root `.gitignore` excludes the real config file.
- Copy `firebase/firebase.json.example` to root `firebase.json`.
- Copy `firebase/.firebaserc.example` to root `.firebaserc` and set your project ID.
- These files are templates. Do not add real project values to this public repo.

## Security requirements before cutover

1. Verify Firestore rules with the Emulator Suite. Do not rely on UI navigation or
   hidden buttons for authorization.
2. Test that a signed-in user cannot read finance, another client's records,
   another employee's private notifications, or unassigned leads/tasks.
3. Test role escalation, inactive accounts, deleting another user, and direct REST
   requests. Every unauthorized operation must be denied by Rules.
4. Use stable Firebase UIDs for assignment and client ownership. Names and email
   strings alone are not safe record ownership identifiers.
5. Firebase web config is not a server secret. Never ship service-account JSON,
   Admin SDK private keys, database credentials, or other secrets to the browser.
6. The current app stores session hints and a copy of workspace data in localStorage.
   Treat localStorage as untrusted; always derive the signed-in identity from
   Firebase Auth and server-enforced Firestore Rules.

## Password and team-management limitations on Spark

The legacy API stores PBKDF2 password hashes in PostgreSQL and creates/resets other
users' passwords from the server. Firebase Auth cannot import those hashes through
the ordinary web SDK. Create Firebase Auth identities and issue password reset
emails after cutover. On Spark, a browser client cannot securely delete another
Auth user or perform privileged password changes as an Admin SDK. Deactivate the
profile in Firestore to block database access; a true Auth account deletion or
admin reset workflow would require a trusted privileged backend, which is outside
this strict Spark scope.

## Current limitations to resolve in the adapter

- Existing state is one JSON snapshot in `crm_dashboard_state`; move to per-record
  collections described in `SCHEMA.md`.
- Existing UI calls a server endpoint and stores a bearer token. Replace with
  Firebase Auth persistence; do not store Firebase ID tokens manually in
  localStorage.
- Worker and Client views are server-filtered today. Recreate filtering with
  Firestore queries plus Security Rules; never fetch all records and filter only
  in JavaScript.
- Existing role-based update logic in Python must be reproduced with
  field-level Firestore Rules.
- Existing dashboard supports 2 MB state payloads; Firestore documents max out
  at 1 MiB. Store each entity as an independent document.
- Document metadata exists in CRM UI, but uploads are not migrated in this phase.

## Rollback

See [ROLLBACK.md](./ROLLBACK.md). The old Vercel deployment and Supabase project
must remain untouched until a separately approved production cutover.
