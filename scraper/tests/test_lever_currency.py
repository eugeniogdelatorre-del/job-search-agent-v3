"""H4 (REVIEW.md, 2026-05-20): lever.py passes non-USD salaries through as
if they were USD, causing GBP/EUR amounts to inflate scores.

Fix: if salaryRange.currency is present and not USD/empty, treat the
salary as unlisted (null out min/max/source) rather than passing the
foreign-currency amount to the scorer.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from scraper.parsers import lever


def _make_session(payload: list[dict]) -> MagicMock:
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    session.get.return_value = resp
    return session


_SOURCE = {"url": "https://jobs.lever.co/acme", "name": "Acme", "category": "Tech"}

_BASE_POST = {
    "text": "Software Engineer",
    "categories": {"location": "Remote"},
    "hostedUrl": "https://jobs.lever.co/acme/123",
    "descriptionPlain": "Great role.",
}


def test_usd_salary_passes_through():
    """USD salary must be extracted normally."""
    post = {**_BASE_POST, "salaryRange": {"min": 80000, "max": 120000, "currency": "USD"}}
    jobs = lever.parse(_make_session([post]), _SOURCE)
    assert len(jobs) == 1
    assert jobs[0]["salary_min_usd"] == 80000
    assert jobs[0]["salary_max_usd"] == 120000
    assert jobs[0]["salary_source"] == "listed"


def test_empty_currency_passes_through():
    """Empty-string currency is treated as USD (common in older postings)."""
    post = {**_BASE_POST, "salaryRange": {"min": 70000, "max": 100000, "currency": ""}}
    jobs = lever.parse(_make_session([post]), _SOURCE)
    assert len(jobs) == 1
    assert jobs[0]["salary_min_usd"] == 70000
    assert jobs[0]["salary_source"] == "listed"


def test_missing_currency_passes_through():
    """No currency field at all → treat as USD."""
    post = {**_BASE_POST, "salaryRange": {"min": 60000, "max": 90000}}
    jobs = lever.parse(_make_session([post]), _SOURCE)
    assert len(jobs) == 1
    assert jobs[0]["salary_min_usd"] == 60000
    assert jobs[0]["salary_source"] == "listed"


def test_gbp_salary_is_nulled_out():
    """GBP salary must NOT pass through — null out all three salary fields."""
    post = {**_BASE_POST, "salaryRange": {"min": 50000, "max": 80000, "currency": "GBP"}}
    jobs = lever.parse(_make_session([post]), _SOURCE)
    assert len(jobs) == 1, "Job itself must still be included (just without salary)"
    assert jobs[0]["salary_min_usd"] is None, "GBP min must be nulled"
    assert jobs[0]["salary_max_usd"] is None, "GBP max must be nulled"
    assert jobs[0]["salary_source"] is None, "GBP salary_source must be None"


def test_eur_salary_is_nulled_out():
    """EUR salary must be nulled out."""
    post = {**_BASE_POST, "salaryRange": {"min": 60000, "max": 95000, "currency": "EUR"}}
    jobs = lever.parse(_make_session([post]), _SOURCE)
    assert len(jobs) == 1
    assert jobs[0]["salary_min_usd"] is None
    assert jobs[0]["salary_source"] is None


def test_lowercase_usd_passes_through():
    """Currency matching is case-insensitive (some APIs return 'usd')."""
    post = {**_BASE_POST, "salaryRange": {"min": 90000, "max": 130000, "currency": "usd"}}
    jobs = lever.parse(_make_session([post]), _SOURCE)
    assert len(jobs) == 1
    assert jobs[0]["salary_min_usd"] == 90000
    assert jobs[0]["salary_source"] == "listed"
