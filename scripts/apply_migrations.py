"""Apply the SQL migrations under scraper/sql/ and web/sql/ to Supabase.

The supabase-py client used by the rest of the project speaks PostgREST,
which doesn't allow DDL. To apply migrations you need a direct Postgres
connection. This script wraps psycopg to do that:

  1. Discovers migration files in dependency order:
       scraper/sql/*.sql
       web/sql/*.sql
     Each directory is sorted by filename so the 001/002/... prefix
     determines order within a directory.

  2. Connects via DATABASE_URL or SUPABASE_DB_URL (the Postgres
     connection string from Supabase → Project Settings → Database →
     Connection string, "URI" tab — NOT the API URL).

  3. Tracks applied migrations in a `schema_migrations` table it
     creates on first run. Subsequent invocations skip migrations
     already applied (filename-based key). Safe to re-run.

  4. Runs each migration in a single transaction. Any error aborts
     that file and rolls it back; previously-applied files stay
     applied.

Usage:
    # Set this once in your shell. Get the value from:
    # Supabase → Project Settings → Database → Connection string → URI
    export DATABASE_URL='postgresql://postgres:[PASSWORD]@db.[REF].supabase.co:5432/postgres'

    python scripts/apply_migrations.py               # apply pending
    python scripts/apply_migrations.py --dry         # print plan, don't run
    python scripts/apply_migrations.py --status      # show applied/pending
    python scripts/apply_migrations.py --rerun NAME  # force re-apply one
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import psycopg  # type: ignore
except ImportError:
    print(
        "  [fatal] psycopg not installed. Run: pip install 'psycopg[binary]'",
        file=sys.stderr,
    )
    sys.exit(2)


REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_DIRS = [
    REPO_ROOT / "scraper" / "sql",
    REPO_ROOT / "web" / "sql",
]
TRACKING_TABLE = "schema_migrations"


def _conn_string() -> str:
    """Return the Postgres connection string from env. Accepts a few
    common variable names — Supabase ships ``DATABASE_URL`` in their
    docs, but folks often set ``SUPABASE_DB_URL`` or ``POSTGRES_URL``
    to avoid colliding with non-Supabase libraries.
    """
    for key in ("DATABASE_URL", "SUPABASE_DB_URL", "POSTGRES_URL"):
        v = os.environ.get(key)
        if v:
            return v
    print(
        "  [fatal] no Postgres connection string in env.\n"
        "  Set DATABASE_URL to the Supabase Postgres URI from:\n"
        "    Project Settings → Database → Connection string → URI\n"
        "  Example: postgresql://postgres:<password>@db.<ref>.supabase.co:5432/postgres",
        file=sys.stderr,
    )
    sys.exit(2)


def _discover_migrations() -> list[tuple[str, Path]]:
    """Return [(migration_name, path)] in apply order.

    ``migration_name`` is "<dir>/<filename>" so the same filename in
    scraper/sql and web/sql doesn't collide in the tracking table.
    """
    out: list[tuple[str, Path]] = []
    for d in MIGRATION_DIRS:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.sql")):
            rel = f.relative_to(REPO_ROOT).as_posix()
            out.append((rel, f))
    return out


def _ensure_tracking_table(conn) -> None:
    """Create schema_migrations if it doesn't exist. Idempotent."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            create table if not exists {TRACKING_TABLE} (
                name text primary key,
                applied_at timestamptz not null default now()
            )
            """
        )
        conn.commit()


def _applied_names(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(f"select name from {TRACKING_TABLE}")
        return {r[0] for r in cur.fetchall()}


def _apply_one(conn, name: str, path: Path, *, force: bool = False) -> None:
    sql = path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        try:
            cur.execute(sql)
            if force:
                # Refresh the timestamp on re-application.
                cur.execute(
                    f"insert into {TRACKING_TABLE}(name, applied_at) values (%s, now()) "
                    "on conflict (name) do update set applied_at = excluded.applied_at",
                    (name,),
                )
            else:
                cur.execute(
                    f"insert into {TRACKING_TABLE}(name) values (%s) "
                    "on conflict (name) do nothing",
                    (name,),
                )
            conn.commit()
            print(f"  ✓ {name}")
        except Exception as e:
            conn.rollback()
            print(f"  ✗ {name}\n     {type(e).__name__}: {e}", file=sys.stderr)
            raise


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="print plan, don't execute")
    ap.add_argument("--status", action="store_true", help="show applied vs pending")
    ap.add_argument("--rerun", help="force re-apply one migration by name (e.g. scraper/sql/001_source_states_rpc.sql)")
    args = ap.parse_args()

    plan = _discover_migrations()
    if not plan:
        print("  no .sql files found in scraper/sql/ or web/sql/")
        return 0

    if args.dry and not args.rerun:
        print("Migration plan (not connecting to DB):")
        for name, _ in plan:
            print(f"  - {name}")
        return 0

    conn_str = _conn_string()
    # Mask password in displayed string.
    display = conn_str
    if "@" in display:
        prefix, rest = display.split("@", 1)
        if ":" in prefix:
            user_part = prefix.rsplit(":", 1)[0]
            display = f"{user_part}:***@{rest}"
    print(f"  connecting to {display}")

    with psycopg.connect(conn_str, autocommit=False) as conn:
        _ensure_tracking_table(conn)
        applied = _applied_names(conn)

        if args.status:
            print("\nApplied:")
            for name, _ in plan:
                mark = "✓" if name in applied else " "
                print(f"  [{mark}] {name}")
            extra = applied - {n for n, _ in plan}
            if extra:
                print("\nApplied but not in current plan (orphans):")
                for name in sorted(extra):
                    print(f"  [?] {name}")
            return 0

        if args.rerun:
            target = next((p for p in plan if p[0] == args.rerun), None)
            if not target:
                print(f"  [fatal] migration not found in plan: {args.rerun}", file=sys.stderr)
                return 3
            print(f"\nForce re-applying {args.rerun}:")
            _apply_one(conn, target[0], target[1], force=True)
            return 0

        pending = [p for p in plan if p[0] not in applied]
        if not pending:
            print("  nothing to do — all migrations already applied")
            return 0
        print(f"\nApplying {len(pending)} pending migration(s):")
        for name, path in pending:
            _apply_one(conn, name, path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
