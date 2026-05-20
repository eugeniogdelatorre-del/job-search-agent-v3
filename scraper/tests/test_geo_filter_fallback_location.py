"""M7 (REVIEW.md, 2026-05-20): geo_filter._resolve_candidate_location
had "Buenos Aires, Argentina" hardcoded as the last-resort fallback.

Fine for the single-tenant Eugenio use-case, but breaks for other users
(Federico/Ana or future multi-tenant) if AI and regex extraction both fail.

Fix: step 4 reads from GEO_FALLBACK_LOCATION env var, defaulting to
the Buenos Aires constant only when the env var is absent.
"""
from __future__ import annotations

import os
from unittest.mock import patch, MagicMock

from scraper import geo_filter


def test_fallback_default_is_buenos_aires(monkeypatch):
    """Without GEO_FALLBACK_LOCATION set, the fallback is Buenos Aires."""
    monkeypatch.delenv("GEO_FALLBACK_LOCATION", raising=False)

    with patch.object(geo_filter, "_ai_extract_candidate_location", return_value=""):
        with patch.object(geo_filter, "_regex_extract_candidate_location", return_value=""):
            result = geo_filter._resolve_candidate_location(MagicMock(), "some resume text")

    assert result == "Buenos Aires, Argentina"


def test_fallback_reads_from_env_var(monkeypatch):
    """GEO_FALLBACK_LOCATION overrides the hardcoded Buenos Aires default."""
    monkeypatch.setenv("GEO_FALLBACK_LOCATION", "London, UK")

    with patch.object(geo_filter, "_ai_extract_candidate_location", return_value=""):
        with patch.object(geo_filter, "_regex_extract_candidate_location", return_value=""):
            result = geo_filter._resolve_candidate_location(MagicMock(), "some resume text")

    assert result == "London, UK"


def test_ai_extraction_takes_precedence_over_fallback(monkeypatch):
    """AI extraction (step 2) wins over the env-var fallback."""
    monkeypatch.setenv("GEO_FALLBACK_LOCATION", "London, UK")

    with patch.object(geo_filter, "_ai_extract_candidate_location", return_value="Berlin, Germany"):
        with patch.object(geo_filter, "_regex_extract_candidate_location", return_value=""):
            result = geo_filter._resolve_candidate_location(MagicMock(), "some resume text")

    assert result == "Berlin, Germany"
