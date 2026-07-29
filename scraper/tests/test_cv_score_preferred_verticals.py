"""Multi-industry expansion (2026-06-04): the AI scorer must downgrade the
web3 bonus from +15 to +5 and apply it to ANY of the 5 preferred verticals
(web3, fintech, AI, SaaS, gaming) rather than web3 alone. Ranking is otherwise
CV-driven.
"""
from __future__ import annotations

from scraper.cv_score import SYSTEM_PREFIX


def test_web3_mega_bonus_removed():
    # The old flat +15 web3 adjustment must be gone everywhere in the rubric.
    assert "+15" not in SYSTEM_PREFIX


def test_preferred_industries_recognised():
    low = SYSTEM_PREFIX.lower()
    for kw in ("fintech", "saas", "gaming"):
        assert kw in low, f"{kw} not referenced in the scoring rubric"


def test_preferred_vertical_bonus_is_five():
    # A +5 preferred-vertical adjustment must be present.
    assert "+5" in SYSTEM_PREFIX
