"""Load sources.json and expose group selection.

sources.json preserves v2's 6 semantic groups. For v3 matrix execution we
collapse those to two balanced super-groups:
    v3 group 1 = v2 groups 1 + 2 + 3   (Mega-caps / L1-L2, DeFi / CEX, Gaming / AI / Infra)
    v3 group 2 = v2 groups 4 + 5 + 6   (Job boards, VC / niche, X feeds — filtered later)

X_Feed sources from v2 group 6 are NOT filtered here. They pass through so
sources_health still records the attempt; the drop happens in the cleanup
pipeline (scrape.py) where junk filtering lives.
"""
from __future__ import annotations

import json
from pathlib import Path

SOURCES_PATH = Path(__file__).parent / "sources.json"

# v2 group key -> v3 super-group number.
V3_GROUP_MAP: dict[str, int] = {
    "group_1": 1,
    "group_2": 1,
    "group_3": 1,
    "group_4": 2,
    "group_5": 2,
    "group_6": 2,
}


def load_sources_file(path: Path = SOURCES_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_sources_for_group(group_num: int, path: Path = SOURCES_PATH) -> list[dict]:
    """Return the flat list of source dicts for v3 group 1 or 2."""
    if group_num not in (1, 2):
        raise ValueError(f"group_num must be 1 or 2, got {group_num}")
    data = load_sources_file(path)
    out: list[dict] = []
    for v2_key, group in data["groups"].items():
        if V3_GROUP_MAP.get(v2_key) != group_num:
            continue
        for src in group["sources"]:
            out.append({**src, "_v2_group": v2_key})
    return out


def get_all_sources(path: Path = SOURCES_PATH) -> list[dict]:
    return get_sources_for_group(1, path) + get_sources_for_group(2, path)
