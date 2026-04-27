"""Tests for greenhouse parser — EU endpoint support."""
from scraper.parsers import greenhouse


def test_us_slug_extraction():
    url = "https://boards.greenhouse.io/ripple"
    slug, is_eu = greenhouse._extract_slug(url)
    assert slug == "ripple"
    assert is_eu is False


def test_eu_slug_extraction():
    url = "https://boards.eu.greenhouse.io/acmecorp"
    slug, is_eu = greenhouse._extract_slug(url)
    assert slug == "acmecorp"
    assert is_eu is True


def test_eu_api_slug_extraction():
    url = "https://boards-api.eu.greenhouse.io/acmecorp"
    slug, is_eu = greenhouse._extract_slug(url)
    assert slug == "acmecorp"
    assert is_eu is True


def test_unknown_url_returns_none():
    slug, is_eu = greenhouse._extract_slug("https://example.com/jobs")
    assert slug is None
    assert is_eu is False


def test_can_parse_eu_url():
    assert greenhouse.can_parse({"url": "https://boards.eu.greenhouse.io/acmecorp"}) is True


def test_can_parse_us_url():
    assert greenhouse.can_parse({"url": "https://boards.greenhouse.io/ripple"}) is True


def test_cannot_parse_unrelated_url():
    assert greenhouse.can_parse({"url": "https://example.com"}) is False
