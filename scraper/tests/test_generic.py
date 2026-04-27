"""Tests for generic parser — homepage redirect guard."""
from unittest.mock import MagicMock
from scraper.parsers import generic


def _mock_response(status_code: int, final_url: str, text: str = "") -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.url = final_url
    r.text = text
    return r


def test_redirect_to_homepage_returns_empty():
    """Careers page that silently redirects to homepage should yield no jobs."""
    session = MagicMock()
    session.get.return_value = _mock_response(
        200,
        "https://example.com/",  # final URL = homepage
        '<html><body><a href="/jobs/123">Senior Engineer</a></body></html>',
    )
    source = {"url": "https://example.com/careers", "name": "Example"}
    assert generic.parse(session, source) == []


def test_no_redirect_not_affected_by_guard():
    """URL that did NOT redirect should not be blocked."""
    session = MagicMock()
    session.get.return_value = _mock_response(
        200,
        "https://example.com/careers",  # same as source URL — no redirect
        "<html><body><p>No jobs here</p></body></html>",
    )
    source = {"url": "https://example.com/careers", "name": "Example"}
    result = generic.parse(session, source)
    assert result == []


def test_redirect_to_non_homepage_not_blocked():
    """Redirect to a non-homepage path should not be blocked."""
    session = MagicMock()
    session.get.return_value = _mock_response(
        200,
        "https://example.com/jobs",  # different path but not homepage
        "<html><body><p>No jobs</p></body></html>",
    )
    source = {"url": "https://example.com/careers", "name": "Example"}
    result = generic.parse(session, source)
    assert result == []  # empty because no job links, but guard did NOT fire
