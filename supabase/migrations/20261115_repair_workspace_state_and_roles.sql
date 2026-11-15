-- NCHURE CRM workspace state compatibility repair.
-- REVIEW ONLY: do not apply until Supabase is ACTIVE, a verified backup exists,
-- and the live schema has been inspected.

BEGIN;

CREATE TABLE IF NOT EXISTS public.crm_dashboard_state (
    id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    state jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_by bigint NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Make the expected non-key columns explicit for a pre-existing partial table.
ALTER TABLE public.crm_dashboard_state
    ADD COLUMN IF NOT EXISTS state jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE public.crm_dashboard_state
    ADD COLUMN IF NOT EXISTS updated_by bigint NULL;
ALTER TABLE public.crm_dashboard_state
    ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

DO $$
BEGIN
    IF to_regclass('public.crm_users') IS NULL THEN
        RAISE EXCEPTION 'public.crm_users is missing; verify the base CRM migration first';
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

-- The original migration permitted eight roles, but the API supports a larger
-- TEAM_ROLES set. API endpoints validate role names; the DB enforces non-empty.
ALTER TABLE public.crm_users
    DROP CONSTRAINT IF EXISTS crm_users_role_check;
ALTER TABLE public.crm_users
    DROP CONSTRAINT IF EXISTS crm_users_role_nonempty_check;
ALTER TABLE public.crm_users
    ADD CONSTRAINT crm_users_role_nonempty_check
    CHECK (length(btrim(role)) > 0);

ALTER TABLE public.crm_dashboard_state ENABLE ROW LEVEL SECURITY;

-- PostgreSQL access is server-side only. Do not grant browser roles direct access.
COMMIT;
