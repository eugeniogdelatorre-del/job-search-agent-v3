"""M9 (REVIEW.md, 2026-05-20): score.py _HOURLY regex allows \$? so a
stray "20h" or "40h/week" in a description can be parsed as $20/hr or
$40/hr, triggering the hourly gate on legitimate job descriptions.

Fix: require a leading dollar sign ($) to anchor the hourly match.
"""
from __future__ import annotations

from scraper.score import _HOURLY


def test_dollar_amount_per_hour_matches():
    """$20/hr must match as usual."""
    assert _HOURLY.search("$20/hr") is not None
    assert _HOURLY.search("$15-25/hour") is not None
    assert _HOURLY.search("$50/h") is not None


def test_hours_without_dollar_does_not_match():
    """'40h', '20h', '8h' without a dollar sign must NOT match."""
    assert _HOURLY.search("40h/week schedule") is None, \
        "'40h' without $ must not trigger hourly gate"
    assert _HOURLY.search("20h part-time") is None, \
        "'20h' without $ must not trigger hourly gate"
    assert _HOURLY.search("requires 8h/day commitment") is None, \
        "'8h/day' must not match as hourly wage"


def test_bare_rate_without_dollar_does_not_match():
    """The actual false-positive the review found: 'digits/hr' with no dollar."""
    assert _HOURLY.search("15/hr") is None, \
        "'15/hr' without $ must not trigger hourly gate"
    assert _HOURLY.search("20/hour") is None, \
        "'20/hour' without $ must not trigger hourly gate"
    assert _HOURLY.search("pay rate is 40/h") is None, \
        "'40/h' without $ must not trigger hourly gate"


def test_range_with_dollar_matches():
    """$30-50/hr range format still matches."""
    assert _HOURLY.search("$30-50/hr") is not None


def test_description_with_hour_count_is_safe():
    """A description mentioning work hours without '$' must not gate the job."""
    desc = "This role requires 40h per week. The team works 8h/day in a hybrid setup."
    assert _HOURLY.search(desc) is None, \
        "Work-hours description without $ must not be parsed as hourly wage"
