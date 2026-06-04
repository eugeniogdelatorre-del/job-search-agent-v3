"""Bug (2026-06-04 review #3): web3career._parse_salary multiplies BOTH bounds
by 1000 whenever the *entire* input string contains the letter "k" anywhere —
including non-suffix occurrences like a word ("Marketing", "think"). That turns
a bare "$50 - $80" into "$50,000 - $80,000".

Fix: tie each ×1000 to that number's own trailing "k" suffix.
"""
from __future__ import annotations

from scraper.parsers.web3career import _parse_salary


def test_stray_k_in_text_does_not_multiply():
    # "Marketing" contains a 'k' but neither number has a k-suffix → not a salary.
    assert _parse_salary("$50 - $80 Marketing") == (None, None, None)


def test_k_suffix_still_multiplies():
    """Regression: genuine '$50k - $80k' must annualise to 50000-80000."""
    assert _parse_salary("$50k - $80k") == (50000, 80000, "listed")


def test_plain_large_numbers_pass_through():
    """No k anywhere → numbers used as-is."""
    assert _parse_salary("$120000 - $150000") == (120000, 150000, "listed")
