# Deployment checklist

- [x] Supabase migration add_legacy_crm_compatible_tables applied.
- [ ] Set DATABASE_URL using the Supabase Transaction Pooler connection string (server-side only).
- [ ] Set a unique random JWT_SECRET (32+ characters).
- [ ] Set INITIAL_ADMIN_EMAIL, INITIAL_ADMIN_PASSWORD (14+ characters), and optional INITIAL_ADMIN_NAME.
- [ ] Import or connect kennyjeron/nchure-crm in Vercel.
- [ ] Redeploy and verify /health reports database_connected: true.
- [ ] Log in and test with non-sensitive records.
- [ ] Remove INITIAL_ADMIN_PASSWORD from Vercel after the first account is created.
- [ ] Do not expose this MVP to real customer data until tenant isolation, RBAC, rate limits, and security tests are complete.
