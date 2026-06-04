"""Bug (2026-06-04 review #4): getonbrd._normalize_salary only annualises
(×12) when the UPPER bound is present and below the monthly threshold. A
listing with only a lower bound (e.g. $3,000/mo, max absent) is left as
$3,000/yr and then silently rejected by score.py's $30k floor.

Fix: decide monthly-vs-annual from whichever bound is present, and ×12 every
present bound.
"""
from __future__ import annotations

from scraper.parsers.getonbrd import _normalize_salary


def test_min_only_monthly_is_annualised():
    # $3,000/mo with no max → should become $36,000/yr.
    assert _normalize_salary(3000, None) == (36000, None)


def test_both_bounds_monthly_still_annualised():
    """Regression: both bounds monthly → both ×12."""
    assert _normalize_salary(3000, 5000) == (36000, 60000)


def test_annual_bounds_unchanged():
    """Regression: already-annual salaries pass through untouched."""
    assert _normalize_salary(50000, 80000) == (50000, 80000)


def test_no_bounds():
    assert _normalize_salary(None, None) == (None, None)
