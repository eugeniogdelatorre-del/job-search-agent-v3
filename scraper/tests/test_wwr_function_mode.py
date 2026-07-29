"""Multi-industry expansion (2026-06-04): the WWR parser hard-filtered its feed
to web3 keywords, so it could never surface non-crypto roles. Add a
`wwr_filter: "function"` source mode that keeps target-FUNCTION roles across ALL
industries instead. Default (no field) keeps the web3 filter for back-compat.
"""
from __future__ import annotations

from scraper.parsers.weworkremotely import _item_matches


def test_function_mode_keeps_target_functions():
    src = {"wwr_filter": "function"}
    assert _item_matches(src, "Acme: Growth Marketing Manager") is True
    assert _item_matches(src, "Fintech Co: Community Manager") is True


def test_function_mode_drops_offtarget_roles():
    src = {"wwr_filter": "function"}
    assert _item_matches(src, "Acme: Senior Backend Engineer (Rust)") is False


def test_default_mode_still_web3_filtered():
    # No wwr_filter → existing web3 behaviour preserved.
    assert _item_matches({}, "Solana: DeFi protocol engineer") is True
    assert _item_matches({}, "Bakery: Marketing Manager") is False
