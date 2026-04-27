"""Tests for teamtailor RSS parser."""
from unittest.mock import MagicMock
from scraper.parsers import teamtailor

_RSS_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Acme Jobs</title>
    <item>
      <title>Backend Engineer</title>
      <link>https://acme.teamtailor.com/jobs/12345-backend-engineer</link>
      <description>&lt;p&gt;Great backend role&lt;/p&gt;</description>
    </item>
    <item>
      <title>Frontend Developer</title>
      <link>https://acme.teamtailor.com/jobs/67890-frontend-developer</link>
      <description>React role</description>
    </item>
  </channel>
</rss>"""

_EMPTY_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>No Jobs</title></channel></rss>"""


def _mock_resp(status: int, content: bytes) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.content = content
    return r


def test_parses_two_jobs():
    session = MagicMock()
    session.get.return_value = _mock_resp(200, _RSS_FEED)
    source = {"url": "https://acme.teamtailor.com/jobs", "name": "Acme", "category": "Gaming"}
    results = teamtailor.parse(session, source)

    assert len(results) == 2
    assert results[0]["title"] == "Backend Engineer"
    assert results[0]["apply_url"] == "https://acme.teamtailor.com/jobs/12345-backend-engineer"
    assert results[0]["company"] == "Acme"
    assert results[0]["category"] == "Gaming"
    assert "Great backend role" in (results[0]["description"] or "")
    assert results[1]["title"] == "Frontend Developer"


def test_empty_feed_returns_empty_list():
    session = MagicMock()
    session.get.return_value = _mock_resp(200, _EMPTY_RSS)
    source = {"url": "https://acme.teamtailor.com/jobs", "name": "Acme"}
    assert teamtailor.parse(session, source) == []


def test_raises_on_http_error():
    session = MagicMock()
    session.get.return_value = _mock_resp(404, b"")
    source = {"url": "https://acme.teamtailor.com/jobs", "name": "Acme"}
    import pytest
    with pytest.raises(RuntimeError, match="teamtailor RSS 404"):
        teamtailor.parse(session, source)


def test_slug_extraction():
    assert teamtailor._extract_slug("https://acme.teamtailor.com/jobs") == "acme"
    assert teamtailor._extract_slug("https://example.com") is None


def test_can_parse():
    assert teamtailor.can_parse({"url": "https://acme.teamtailor.com/jobs"}) is True
    assert teamtailor.can_parse({"url": "https://example.com"}) is False
