"""Multi-industry expansion (2026-06-04): Get on Board pulled only the
'programming' category. Parametrise it via an optional `getonbrd_category`
source field so we can also pull marketing/sales/community roles (any
industry), defaulting to 'programming' for backwards compatibility.
"""
from __future__ import annotations

from scraper.parsers.getonbrd import _category


def test_default_category_is_programming():
    assert _category({"url": "https://www.getonbrd.com/jobs"}) == "programming"


def test_custom_category_honoured():
    assert _category({"url": "https://www.getonbrd.com/empleos-marketing",
                      "getonbrd_category": "marketing-sales"}) == "marketing-sales"
