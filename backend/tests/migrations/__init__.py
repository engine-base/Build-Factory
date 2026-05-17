"""backend/tests/migrations — static validation of supabase/migrations/*.sql.

Tests here read the SQL files as text and assert on shape (CREATE TABLE,
ALTER TABLE, RLS policies, idempotency guards, etc) without requiring a
live Postgres connection. This keeps Wave-4 drift-fix tasks unit-testable
in CI without infrastructure setup.
"""
