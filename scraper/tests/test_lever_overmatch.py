"""Bug (2026-06-04 review #8): the lever parser's bare ``lever.co/<path>``
branch claims ANY path on Lever's marketing domain, so ``lever.co/about`` and
``lever.co/blog`` are treated as boards — they hit api.lever.co, 404, and mark
the source failed.

Fix: exclude known Lever marketing paths from the bare-domain branch. The
legitimate bare form (``lever.co/Onehouse`` — a real source) must still match.
"""
from __future__ import annotations

from scraper.parsers.lever import can_parse


def test_marketing_about_page_not_matched():
    assert can_parse({"url": "https://www.lever.co/about"}) is False


def test_marketing_blog_page_not_matched():
    assert can_parse({"url": "https://lever.co/blog/hiring"}) is False


def test_real_bare_domain_board_still_matched():
    """Regression: lever.co/Onehouse is a live source and must still parse."""
    assert can_parse({"url": "https://lever.co/Onehouse"}) is True


def test_jobs_subdomain_still_matched():
    assert can_parse({"url": "https://jobs.lever.co/celestia"}) is True


def test_company_subdomain_still_matched():
    assert can_parse({"url": "https://acme.lever.co/"}) is True
