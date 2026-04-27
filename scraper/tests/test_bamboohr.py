"""Tests for bamboohr parser."""
from unittest.mock import MagicMock
from scraper.parsers import bamboohr

_LIST_PAYLOAD = {
    "result": [
        {"id": "42", "jobOpeningName": "Senior Engineer"},
    ]
}

_DETAIL_PAYLOAD = {
    "result": {
        "jobOpening": {
            "jobOpeningName": "Senior Engineer",
            "description": "<p>Great role with <b>impact</b></p>",
            "location": {"name": "Remote"},
            "jobOpeningShareUrl": "https://acme.bamboohr.com/careers/42",
        }
    }
}


def _mock_resp(status: int, data: dict) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.json.return_value = data
    return r


def test_parses_jobs_with_detail():
    session = MagicMock()
    session.get.side_effect = [
        _mock_resp(200, _LIST_PAYLOAD),
        _mock_resp(200, _DETAIL_PAYLOAD),
    ]
    source = {"url": "https://acme.bamboohr.com/careers", "name": "Acme", "category": "DeFi"}
    results = bamboohr.parse(session, source)

    assert len(results) == 1
    job = results[0]
    assert job["title"] == "Senior Engineer"
    assert job["company"] == "Acme"
    assert job["location"] == "Remote"
    assert job["apply_url"] == "https://acme.bamboohr.com/careers/42"
    assert "Great role" in (job["description"] or "")
    assert job["category"] == "DeFi"


def test_falls_back_when_detail_fails():
    """If the detail request returns non-200, job is still emitted with minimal info."""
    session = MagicMock()
    session.get.side_effect = [
        _mock_resp(200, _LIST_PAYLOAD),
        _mock_resp(404, {}),
    ]
    source = {"url": "https://acme.bamboohr.com/careers", "name": "Acme"}
    results = bamboohr.parse(session, source)
    assert len(results) == 1
    assert results[0]["title"] == "Senior Engineer"
    assert results[0]["description"] is None


def test_raises_on_list_api_failure():
    session = MagicMock()
    session.get.return_value = _mock_resp(403, {})
    source = {"url": "https://acme.bamboohr.com/careers", "name": "Acme"}
    import pytest
    with pytest.raises(RuntimeError, match="bamboohr list API 403"):
        bamboohr.parse(session, source)


def test_slug_extraction():
    assert bamboohr._extract_slug("https://acme.bamboohr.com/careers") == "acme"
    assert bamboohr._extract_slug("https://acme.bamboohr.com/careers/list") == "acme"
    assert bamboohr._extract_slug("https://example.com") is None


def test_can_parse():
    assert bamboohr.can_parse({"url": "https://acme.bamboohr.com/careers"}) is True
    assert bamboohr.can_parse({"url": "https://example.com"}) is False
