"""C5 (REVIEW.md, 2026-05-19): scrape's upsert must not overwrite
classify's AI-extracted salaries with NULL on every re-scrape.

The PostgREST upsert (``client.table("jobs").upsert(batch,
on_conflict="dedup_key")``) translates to ``INSERT ... ON CONFLICT DO
UPDATE SET col=EXCLUDED.col`` for EVERY column in the payload. When
``_job_to_row`` unconditionally included ``salary_min_usd=None`` /
``salary_max_usd=None`` / ``salary_source=None`` for jobs whose parser
didn't list a salary, the next cron cycle's upsert would null out the
salary that classify.py had just extracted from the description.

Lifecycle of the bug:
  T0  scrape  no listed salary    → row has nulls
  T1  classify  AI finds "$80-120k" → row has $80-120k, source=extracted_by_ai
  T2  scrape (next day) same parser → row's salary fields wiped back to null
  T3  cv_score / archive filter   → role excluded as "no salary"

H17 fixed the symmetric bug inside classify.py (only patch sides that
came back non-null). C5 fixes the inverse: scrape must omit the salary
keys entirely when it didn't extract them, so the EXCLUDED clause has
nothing to overwrite with.
"""
from __future__ import annotations

from scraper.scrape import _job_to_row


_BASE_JOB = {
    "dedup_key": "acme|community-manager|any",
    "title": "Community Manager",
    "company": "Acme",
    "source": "acme",
    "source_tier": 3,
    "last_seen_at": "2026-05-19T00:00:00+00:00",
}


def test_unlisted_salary_is_omitted_from_payload():
    """When the parser didn't extract a salary, the row sent to upsert
    must NOT contain salary_* keys — otherwise EXCLUDED.salary_min_usd
    would wipe the AI-extracted value classify wrote on the previous
    pipeline cycle."""
    job = dict(_BASE_JOB)
    job.update(salary_min_usd=None, salary_max_usd=None, salary_source=None)

    row = _job_to_row(job, 60, {"gate_failed": None})

    assert "salary_min_usd" not in row, (
        "Scrape must not send salary_min_usd when parser didn't list one — "
        "would wipe AI-extracted value via upsert EXCLUDED clause"
    )
    assert "salary_max_usd" not in row
    assert "salary_source" not in row


def test_listed_salary_does_get_written():
    """When the parser DID extract a listed salary, the row must
    include it — scrape is still the authoritative source for
    salary_source='listed'."""
    job = dict(_BASE_JOB)
    job.update(salary_min_usd=80000, salary_max_usd=120000, salary_source="listed")

    row = _job_to_row(job, 60, {"gate_failed": None})

    assert row["salary_min_usd"] == 80000
    assert row["salary_max_usd"] == 120000
    assert row["salary_source"] == "listed"


def test_partial_listed_salary_still_written():
    """Edge case: parser found a min but not a max (or vice versa).
    Treat as 'listed' so scrape keeps authority; classify won't
    second-guess a partially-listed range. The key contract is that
    when salary_source='listed' the salary fields are written."""
    job = dict(_BASE_JOB)
    job.update(salary_min_usd=80000, salary_max_usd=None, salary_source="listed")

    row = _job_to_row(job, 60, {"gate_failed": None})

    assert row["salary_min_usd"] == 80000
    assert row["salary_max_usd"] is None
    assert row["salary_source"] == "listed"
