"""H2 (REVIEW.md, 2026-05-20): dedup_within_run uses strict ``>`` on
source_tier so the FIRST job seen on a tie wins, even if the second
has a richer description and a listed salary. Fix: use a (tier,
has_salary, desc_len) tuple so the richest row always wins on tier ties.
"""
from __future__ import annotations

from scraper.dedup import dedup_within_run


def test_same_tier_prefers_listed_salary():
    """On a source_tier tie the row with a listed salary wins."""
    sparse = {"dedup_key": "k", "source_tier": 2, "description": "short", "salary_min_usd": None}
    rich   = {"dedup_key": "k", "source_tier": 2, "description": "short", "salary_min_usd": 100_000}
    out = dedup_within_run([sparse, rich])
    assert len(out) == 1
    assert out[0] is rich, "Tied source_tier: listed salary must win over no salary"


def test_same_tier_prefers_longer_description():
    """On a source_tier tie with both missing salary, the longer description wins."""
    sparse = {"dedup_key": "k", "source_tier": 2, "description": "short", "salary_min_usd": None}
    rich   = {"dedup_key": "k", "source_tier": 2, "description": "a" * 3000, "salary_min_usd": None}
    out = dedup_within_run([sparse, rich])
    assert len(out) == 1
    assert out[0] is rich, "Tied source_tier: longer description must win"


def test_same_tier_prefers_longer_description_and_listed_salary():
    """Combined tiebreaker: salary + description together."""
    sparse = {"dedup_key": "k", "source_tier": 2, "description": "short", "salary_min_usd": None}
    rich   = {"dedup_key": "k", "source_tier": 2, "description": "a" * 3000, "salary_min_usd": 100_000}
    out = dedup_within_run([sparse, rich])
    assert len(out) == 1
    assert out[0] is rich, "Tied source_tier must break toward listed-salary + longer description"


def test_higher_tier_still_wins_over_richer_lower_tier():
    """Tier is the primary sort key — a tier-3 sparse row beats a tier-2 rich one."""
    tier2_rich = {"dedup_key": "k", "source_tier": 2, "description": "a" * 5000, "salary_min_usd": 200_000}
    tier3_sparse = {"dedup_key": "k", "source_tier": 3, "description": "x", "salary_min_usd": None}
    out = dedup_within_run([tier2_rich, tier3_sparse])
    assert len(out) == 1
    assert out[0] is tier3_sparse, "source_tier is the primary tiebreaker"


def test_no_dedup_key_passthrough_unaffected():
    """Jobs without a valid dedup_key must not be dropped."""
    j1 = {"dedup_key": None, "source_tier": 2}
    j2 = {"dedup_key": "|",  "source_tier": 2}
    out = dedup_within_run([j1, j2])
    assert len(out) == 2
