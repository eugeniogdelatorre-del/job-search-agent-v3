"""One-shot skill-graph extractor for an active CV.

Turns the parsed CV text into a structured graph the cv_score prompt
can score against deterministically. Replaces the "dump full CV text
into every batch" approach with "extract once, score against a
structured grid forever".

Why this matters:
    * The model used to re-read the CV every batch and re-infer your
      seniority/skills each time. Same CV + same job → slightly
      different scores run-to-run.
    * The cv_score prompt now sees a structured object, so it can't
      hallucinate skills you don't have ("the job mentions Rust →
      assume the candidate has Rust" was a real failure mode).
    * Per-batch prompt size drops ~80% — cache hit rate stays high and
      Anthropic spend goes down with it.

The result lives in resumes.skill_graph (jsonb, added via
web/sql/006_resumes_skill_graph.sql). cv_score.py reads it; if missing,
falls back to the old parsed_text dump path AND lazily populates the
column from there.

Cost: one non-batch Haiku call per active CV per extraction. ~$0.005.

Usage:
    from scraper.cv_extract import extract_and_store_skill_graph
    graph = extract_and_store_skill_graph(supabase, anthropic, resume_id)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper._anthropic_batch import extract_json as _extract_json

# Same model as the rest of the AI pipeline. Non-batch (~2× cost) but
# tiny — this runs once per CV, not per job.
MODEL = "claude-haiku-4-5-20251001"
MAX_CV_CHARS = 15_000   # cap input so a malformed parse can't blow up

SYSTEM_PROMPT = """\
You are a careful resume analyst. Read a candidate's resume and return a
STRUCTURED skill graph as JSON. Do not invent skills or experience not
clearly supported by the resume text.

Return JSON only — no prose, no code fences, no commentary.
"""

# The schema is verbose on purpose: the model performs better when the
# expected shape is fully spelled out and each enum value is given.
USER_TEMPLATE = """\
Extract the candidate's skill graph from this resume.

Return JSON matching EXACTLY this shape (and ONLY this shape):

{{
  "skills": [
    {{
      "name": "<technology or skill, e.g. Python>",
      "level": "<one of: senior | intermediate | exposure>",
      "years": <integer years, 0 if unclear>,
      "evidence": "<<=80 char quote or paraphrase from the resume>"
    }}
  ],
  "domains": ["<industry or domain, e.g. Web3 infra, B2B SaaS, DevTools>"],
  "seniority_anchor": "<one of: principal | staff | senior | mid | junior | unclear>",
  "location": {{
    "city": "<city, or empty string>",
    "country": "<country, or empty string>"
  }},
  "languages": ["<lang: level, e.g. English: native>"],
  "deal_breakers": ["<short phrases about hard constraints, e.g. 'on-site outside LATAM'>"],
  "preferences": ["<short phrases about preferences, e.g. 'small team', 'Series A-C'>"]
}}

Rules:
1. "level" MUST be exactly one of: "senior", "intermediate", "exposure".
2. "seniority_anchor" MUST be exactly one of: "principal", "staff", "senior", "mid", "junior", "unclear".
3. Cap "skills" at 30 entries, highest-confidence first.
4. Each "evidence" string must be <=80 characters.
5. If a section can't be confidently inferred, return an empty array or empty strings.
6. Do NOT invent skills not in the resume. Conservative > generous.

Resume text:
---
{resume_text}
---
"""


def _allowed_level(v: str) -> str:
    v = (v or "").strip().lower()
    return v if v in ("senior", "intermediate", "exposure") else "exposure"


def _allowed_seniority(v: str) -> str:
    v = (v or "").strip().lower()
    if v in ("principal", "staff", "senior", "mid", "junior", "unclear"):
        return v
    return "unclear"


def _sanitize(graph: dict) -> dict:
    """Coerce model output into the documented shape, dropping garbage
    entries. The cv_score prompt assumes this shape; an unsanitized
    graph could let the model see unexpected keys and degrade scoring.
    """
    out: dict = {
        "skills": [],
        "domains": [],
        "seniority_anchor": "unclear",
        "location": {"city": "", "country": ""},
        "languages": [],
        "deal_breakers": [],
        "preferences": [],
    }

    for s in (graph.get("skills") or [])[:30]:
        if not isinstance(s, dict):
            continue
        name = str(s.get("name") or "").strip()[:60]
        if not name:
            continue
        try:
            years = int(s.get("years") or 0)
        except (TypeError, ValueError):
            years = 0
        out["skills"].append({
            "name": name,
            "level": _allowed_level(s.get("level")),
            "years": max(0, min(50, years)),
            "evidence": str(s.get("evidence") or "").strip()[:80],
        })

    for d in (graph.get("domains") or [])[:15]:
        d = str(d).strip()[:60]
        if d:
            out["domains"].append(d)

    out["seniority_anchor"] = _allowed_seniority(graph.get("seniority_anchor"))

    loc = graph.get("location") or {}
    if isinstance(loc, dict):
        out["location"]["city"] = str(loc.get("city") or "").strip()[:80]
        out["location"]["country"] = str(loc.get("country") or "").strip()[:80]

    for lang in (graph.get("languages") or [])[:10]:
        lang = str(lang).strip()[:60]
        if lang:
            out["languages"].append(lang)

    for db in (graph.get("deal_breakers") or [])[:10]:
        db = str(db).strip()[:120]
        if db:
            out["deal_breakers"].append(db)

    for pref in (graph.get("preferences") or [])[:10]:
        pref = str(pref).strip()[:120]
        if pref:
            out["preferences"].append(pref)

    return out


def extract_skill_graph(anthropic_client, resume_text: str) -> dict | None:
    """Run the extraction. Returns sanitized graph dict or None on failure.

    Fail-soft: any error returns None and the caller falls back to the
    parsed_text path. The cost is small and a retry on the next batch is
    cheap, so we don't bother retrying inline.
    """
    if anthropic_client is None or not resume_text:
        return None
    snippet = resume_text[:MAX_CV_CHARS]
    try:
        msg = anthropic_client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": USER_TEMPLATE.format(resume_text=snippet)}],
        )
    except Exception as e:
        print(f"  [cv_extract] AI call failed: {e}", file=sys.stderr)
        return None

    text = ""
    for block in getattr(msg, "content", []) or []:
        if getattr(block, "type", None) == "text":
            text = (getattr(block, "text", "") or "").strip()
            break

    parsed = _extract_json(text)
    if not isinstance(parsed, dict):
        print(
            f"  [cv_extract] model output did not parse as JSON; first 200 chars: {text[:200]!r}",
            file=sys.stderr,
        )
        return None

    try:
        return _sanitize(parsed)
    except Exception as e:
        print(f"  [cv_extract] sanitize failed: {e}", file=sys.stderr)
        return None


def store_skill_graph(supabase_client, resume_id: str, graph: dict) -> bool:
    """Write the graph to resumes.skill_graph. Tolerates the column not
    existing yet (pre-migration) — returns False without raising, so the
    caller can keep using the parsed_text path.
    """
    if supabase_client is None or not graph:
        return False
    try:
        resp = (
            supabase_client.table("resumes")
            .update({"skill_graph": graph})
            .eq("id", resume_id)
            .execute()
        )
        # supabase-py returns data on representation; an empty result
        # could mean the column doesn't exist (PGRST204 raised) or the
        # row vanished. Either way, we don't block cv_score.
        return bool(getattr(resp, "data", None))
    except Exception as e:
        msg = str(e)
        if "PGRST204" in msg or "42703" in msg or "column" in msg.lower():
            print(
                "  [cv_extract] skill_graph column not deployed yet — "
                "extraction stored only in memory. Apply "
                "web/sql/006_resumes_skill_graph.sql to persist.",
                file=sys.stderr,
            )
        else:
            print(f"  [cv_extract] store_skill_graph failed: {e}", file=sys.stderr)
        return False


def extract_and_store_skill_graph(
    supabase_client,
    anthropic_client,
    resume_id: str,
    resume_text: str,
) -> dict | None:
    """End-to-end: extract, sanitize, persist. Returns the graph or None.

    Called by cv_score.py at the top of a batch if the active resume's
    skill_graph column is null.
    """
    graph = extract_skill_graph(anthropic_client, resume_text)
    if graph is None:
        return None
    store_skill_graph(supabase_client, resume_id, graph)
    return graph


def main() -> int:
    """Manual extraction for one resume id (debugging / manual reprocess).

    Usage:
        python -m scraper.cv_extract <resume_id>
    """
    import argparse
    from scraper import supabase_client
    from scraper._anthropic_batch import get_anthropic_client

    ap = argparse.ArgumentParser(description="Extract a skill graph for one resume.")
    ap.add_argument("resume_id")
    ap.add_argument("--dry", action="store_true", help="print graph to stdout, don't persist")
    args = ap.parse_args()

    sb = supabase_client.get_client()
    if sb is None:
        print("  [fatal] no supabase client", file=sys.stderr)
        return 2

    row = (
        sb.table("resumes")
        .select("id, parsed_text")
        .eq("id", args.resume_id)
        .maybe_single()
        .execute()
    )
    data = getattr(row, "data", None)
    if not data:
        print(f"  [fatal] resume {args.resume_id} not found", file=sys.stderr)
        return 3
    resume_text = (data.get("parsed_text") or "").strip()
    if not resume_text:
        print(f"  [fatal] resume {args.resume_id} has empty parsed_text", file=sys.stderr)
        return 3

    anthropic = get_anthropic_client()
    if anthropic is None:
        return 2

    graph = extract_skill_graph(anthropic, resume_text)
    if graph is None:
        print("  [fatal] extraction returned None", file=sys.stderr)
        return 4

    print(json.dumps(graph, indent=2, ensure_ascii=False))
    if not args.dry:
        store_skill_graph(sb, args.resume_id, graph)
        print(f"  [cv_extract] stored skill_graph for {args.resume_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
