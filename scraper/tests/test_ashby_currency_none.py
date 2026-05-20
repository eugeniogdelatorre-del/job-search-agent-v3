"""L4 (REVIEW.md, 2026-05-20): ashby._parse_compensation has
`(... or "").upper() not in ("USD", "", None)`. The Python `None` in
the allow-set is dead code — the expression always yields a str due to
the trailing `or ""`. The real bug: if the API returns the *string*
`"None"` as the currencyCode, `.upper()` produces `"NONE"`, which is
not in the allow-set, so the tier is skipped and the salary is lost.

Fix: normalise to `.strip().upper()` and add `"NONE"` to the allow-set
(or equivalently replace the dead `None` entry with `"NONE"`).
"""
from __future__ import annotations

from scraper.parsers.ashby import _parse_compensation


def test_string_none_currency_is_treated_as_usd():
    """currencyCode='None' (a string, not Python None) must not null-out salary."""
    comp = [{"currencyCode": "None", "minValue": 50_000, "maxValue": 100_000}]
    assert _parse_compensation(comp) == (50_000, 100_000, "listed"), (
        "String 'None' after .upper() becomes 'NONE'; if that is not in the "
        "allow-set the tier is silently skipped and the salary is lost"
    )


def test_python_none_currency_is_treated_as_usd():
    """currencyCode=None (Python None) must still parse; the `or ''` handles it."""
    comp = [{"currencyCode": None, "minValue": 60_000, "maxValue": 120_000}]
    assert _parse_compensation(comp) == (60_000, 120_000, "listed")


def test_usd_currency_still_passes():
    """Explicit 'USD' must still parse (regression guard)."""
    comp = [{"currencyCode": "USD", "minValue": 80_000, "maxValue": 150_000}]
    assert _parse_compensation(comp) == (80_000, 150_000, "listed")


def test_eur_currency_is_skipped():
    """Non-USD (e.g. EUR) tiers must still be skipped — allow-set unchanged."""
    comp = [{"currencyCode": "EUR", "minValue": 70_000, "maxValue": 130_000}]
    assert _parse_compensation(comp) == (None, None, None)


def test_empty_currency_passes():
    """Empty string currency is allowed (treat as USD/unspecified)."""
    comp = [{"currencyCode": "", "minValue": 40_000, "maxValue": 80_000}]
    assert _parse_compensation(comp) == (40_000, 80_000, "listed")
