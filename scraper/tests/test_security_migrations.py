"""C6 (Supabase security advisor, 2026-05-20): public.schema_migrations had RLS
disabled, exposing the full migration history to unauthenticated callers via
PostgREST (SELECT on the public schema is granted to anon by default).

These tests ensure the fix migration file exists and cannot be silently deleted
or reverted without breaking CI.  They do NOT require a live DB connection.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MIGRATION_FILE = REPO_ROOT / "docs" / "migrations" / "2026-05-20-schema-migrations-rls.sql"


def test_schema_migrations_rls_migration_file_exists():
    """Migration file that enables RLS on schema_migrations must exist in the repo."""
    assert MIGRATION_FILE.exists(), (
        f"Migration file not found: {MIGRATION_FILE}\n"
        "C6 fix requires enabling RLS on public.schema_migrations — "
        "create the migration file and apply it via Supabase."
    )


def test_schema_migrations_rls_migration_contains_enable_rls():
    """Migration SQL must contain the ENABLE ROW LEVEL SECURITY statement."""
    if not MIGRATION_FILE.exists():
        return  # covered by test above; avoid double-failure noise
    content = MIGRATION_FILE.read_text(encoding="utf-8").upper()
    assert "ENABLE ROW LEVEL SECURITY" in content, (
        "Migration must contain ALTER TABLE … ENABLE ROW LEVEL SECURITY"
    )


def test_schema_migrations_rls_migration_targets_correct_table():
    """Migration SQL must reference the schema_migrations table."""
    if not MIGRATION_FILE.exists():
        return
    content = MIGRATION_FILE.read_text(encoding="utf-8").upper()
    assert "SCHEMA_MIGRATIONS" in content, (
        "Migration must target the schema_migrations table, not a different table"
    )
