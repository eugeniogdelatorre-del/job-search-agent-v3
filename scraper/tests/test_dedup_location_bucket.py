"""L7 (REVIEW.md, 2026-05-20): dedup.location_bucket comment claims
"San Francisco, CA" and "San Francisco" map to the same bucket, but
the current implementation produces "san francisco ca" vs "san
francisco" (different strings), so the two postings are NOT collapsed.

Fix: strip the comma-suffix (state/country) before normalising so
"City, ST" and "City" both bucket to "city".
"""
from __future__ import annotations

from scraper.dedup import location_bucket


def test_city_with_state_same_as_city_alone():
    """'San Francisco, CA' must bucket identically to 'San Francisco'."""
    assert location_bucket("San Francisco, CA") == location_bucket("San Francisco"), (
        "'San Francisco, CA' → 'san francisco ca' != 'san francisco'; "
        "the state suffix must be stripped before bucketing"
    )


def test_city_with_country_same_as_city_alone():
    """'New York, USA' must bucket identically to 'New York'."""
    assert location_bucket("New York, USA") == location_bucket("New York")


def test_remote_with_region_still_remote():
    """'Remote, US' still resolves to the 'remote' bucket."""
    assert location_bucket("Remote, US") == "remote"


def test_empty_location_returns_any():
    """None / empty string still returns 'any'."""
    assert location_bucket(None) == "any"
    assert location_bucket("") == "any"


def test_plain_city_unchanged():
    """'Buenos Aires' (no comma) still buckets to 'buenos aires'."""
    assert location_bucket("Buenos Aires") == "buenos aires"


def test_24_char_truncation_preserved():
    """Leading-24-char truncation still applies after stripping suffix."""
    long_city = "A" * 30
    assert location_bucket(long_city) == "a" * 24
