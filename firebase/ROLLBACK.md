# NCHURE CRM — migration rollback and cutover controls

## Current safety boundary

This migration branch is separate from `main`. No Supabase schema, data, secrets,
Vercel environment variables, deployment aliases, custom domains or production
settings have been modified.

## Before any production cutover

- Export the current Firebase-independent local browser data from each browser
  profile that has ever been used for NCHURE CRM.
- Save a Supabase database backup and verify the export can be restored.
- Record current Vercel deployment ID, commit SHA, domains and environment-variable
  names. Do not export secret values into GitHub.
- Deploy the Firebase branch to a preview URL only after its integration tests pass.
- Test Founder login, member lifecycle, Client portal, permissions, CRUD, refresh,
  browser restart, logout, and a second browser/device.
- Compare record counts and sample hashes between exported source and Firestore.
- Keep the production Vercel domain pointed at the old deployment until a separate
  cutover approval is given.

## Rollback

1. Revert the DNS/custom-domain cutover (only after explicit approval) to the
   original Vercel project.
2. Keep the Firebase project and migration branch for investigation; do not delete
   Firebase data during rollback.
3. Restore any records written during the Firebase trial by exporting Firestore
   data and reconciling it with the pre-cutover export. Do not blindly overwrite
   Supabase with a Firebase export.
4. Do not disable or delete the old Supabase project or Vercel project until the
   rollback window has passed and data reconciliation is signed off.

## Approval gates

Production deployment, DNS changes, deleting or pausing old infrastructure,
Supabase migrations, secret rotation, and data deletion are separate actions and
are not authorized by creating this migration branch.
