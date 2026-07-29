"""Multi-industry expansion (2026-06-04): the rule scorer must stop treating
web3 as the only rewarded vertical. vertical_fit should boost ANY of the 5
preferred verticals (web3, fintech, AI, SaaS, gaming), and a non-web3 role in a
target function must clear the warm gate (score_total >= 40) so it reaches the
AI scorer. team_stage should also recognise non-web3 VCs.
"""
from __future__ import annotations

from scraper.score import DEFAULT_CONFIG, score_job, _dim_vertical_fit, _dim_team_stage

VCFG = DEFAULT_CONFIG["dimensions"]["vertical_fit"]
TCFG = DEFAULT_CONFIG["dimensions"]["team_stage"]


def _job(title, desc="", company="Acme", tier=3):
    return {"title": title, "company": company, "description": desc,
            "location": "Remote", "source_tier": tier}


def test_fintech_boosts_vertical():
    score, _ = _dim_vertical_fit(_job("Growth Manager", "a fintech payments company"), VCFG)
    assert score > 50


def test_ai_boosts_vertical():
    score, _ = _dim_vertical_fit(_job("Community Manager", "a machine learning platform"), VCFG)
    assert score > 50


def test_saas_boosts_vertical():
    score, _ = _dim_vertical_fit(_job("Content Lead", "b2b saas developer tools"), VCFG)
    assert score > 50


def test_gaming_boosts_vertical():
    score, _ = _dim_vertical_fit(_job("Community Lead", "a video game studio"), VCFG)
    assert score > 50


def test_web3_still_boosts_vertical():
    """Regression: web3 must remain a rewarded vertical (just no longer the only one)."""
    score, _ = _dim_vertical_fit(_job("Community Manager", "a defi protocol"), VCFG)
    assert score > 50


def test_unpreferred_industry_stays_neutral():
    score, _ = _dim_vertical_fit(_job("Marketing Manager", "a healthcare clinic network"), VCFG)
    assert score == 50


def test_non_web3_vc_boosts_team_stage():
    # "greylock" as an investor, without the generic "backed by" signal.
    score, _ = _dim_team_stage(
        {"title": "x", "company": "y", "description": "greylock is an investor here", "location": ""},
        TCFG,
    )
    assert score > 50


def test_fintech_growth_role_clears_warm_gate():
    total, breakdown = score_job(_job(
        "Growth Manager",
        "Fintech payments startup. Responsibilities: what you'll do. Team size 20.",
    ))
    assert breakdown["gate_failed"] is None
    assert total >= 40
