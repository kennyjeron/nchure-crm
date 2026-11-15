-- NCHURE CRM workspace state compatibility repair.
-- SAFE TO REVIEW: this migration is intentionally NOT applied automatically.
-- Run only after the Supabase project is reachable, a verified backup exists,
-- and the live schema has been inspected against the existing database.

BEGIN;

CREATE TABLE IF NOT EXISTS public.crm_dashboard_state (
    id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    state jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_by bigint NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF to_regclass('public.crm_users') IS NULL THEN
        RAISE EXCEPTION 'public.crm_users is missing; apply and verify the base CRM migration first';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'crm_dashboard_state_updated_by_fkey'
          AND conrelid = 'public.crm_dashboard_state'::regclass
    ) THEN
        ALTER TABLE public.crm_dashboard_state
            ADD CONSTRAINT crm_dashboard_state_updated_by_fkey
            FOREIGN KEY (updated_by) REFERENCES public.crm_users(id)
            ON DELETE SET NULL;
    END IF;
END $$;

-- The original migration allowed eight roles; the API now supports many more.
ALTER TABLE public.crm_users
    DROP CONSTRAINT IF EXISTS crm_users_role_check;
ALTER TABLE public.crm_users
    DROP CONSTRAINT IF EXISTS crm_users_role_nonempty_check;
ALTER TABLE public.crm_users
    ADD CONSTRAINT crm_users_role_nonempty_check
    CHECK (length(btrim(role)) > 0);

ALTER TABLE public.crm_dashboard_state ENABLE ROW LEVEL SECURITY;

-- Server-side PostgreSQL access only. Do not grant browser roles direct access.
COMMIT;
