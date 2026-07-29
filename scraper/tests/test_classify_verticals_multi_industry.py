"""Multi-industry expansion (2026-06-04): the classifier vertical enum must
include the non-web3 preferred industries so non-crypto jobs get an accurate
vertical (used by the dashboard filter and cv_score's industry_fit).
"""
from __future__ import annotations

from scraper.classify import VERTICALS


def test_verticals_include_preferred_industries():
    for v in ("Fintech", "Payments", "AI", "SaaS", "Gaming"):
        assert v in VERTICALS, f"{v} missing from classify VERTICALS"


def test_web3_verticals_retained():
    for v in ("DeFi", "L1", "CEX"):
        assert v in VERTICALS
