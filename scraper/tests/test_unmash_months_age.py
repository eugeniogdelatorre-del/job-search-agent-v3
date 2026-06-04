"""Bug (2026-06-04 review #1): the WWR title-unmasher's age-token regex lists
``\\d+[dmhw]`` before ``\\d+mo``. Because regex alternation is left-biased, a
months-ago badge like ``5mo`` matches only ``5m``, leaving a stray ``o`` glued
to the front of the company group. That single ``o`` then becomes the company
name (and the real company is mis-read as the location).

Fix: order the alternation so ``\\d+mo`` is tried before ``\\d+[dmhw]``.
"""
from __future__ import annotations

from scraper.junk_filters import unmash_aggregator_title


def _mashed(title, age, company, emp, tail):
    return title + age + company + emp + tail


def test_months_age_token_does_not_corrupt_company():
    # Real WWR-style mash with a *months* age badge ("5mo").
    title = "Senior Protocol Engineer for Distributed Systems Team"
    mashed = _mashed(title, "5mo", "Wintermute", "Full-Time", "London")
    assert len(mashed) >= 80  # only long titles are unmashed

    job = {"title": mashed, "company": "we work remotely"}
    out = unmash_aggregator_title(job)

    assert out["company"] == "Wintermute", (
        f"months badge corrupted the company name: got {out['company']!r}"
    )
    assert out["title"] == title


def test_days_age_token_still_works():
    """Regression: a days badge ('5d') must still split correctly."""
    title = "Senior Protocol Engineer for Distributed Systems Team Lead"
    mashed = _mashed(title, "5d", "Wintermute", "Full-Time", "London")
    job = {"title": mashed, "company": "we work remotely"}
    out = unmash_aggregator_title(job)
    assert out["company"] == "Wintermute"
    assert out["title"] == title
