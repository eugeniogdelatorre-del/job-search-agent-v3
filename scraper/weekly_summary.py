"""Weekly summary email — Phase 8d.

Sends Eugenio the top 10 best-matching jobs from the past 7 days, as
scored by the active CV. No AI in this step — the job_scores rows are
already written by cv_score.py. We just query, render HTML, and POST
to Resend.

Per plan §4.3 and §D5:
    - Recipient: eugeniogdelatorre@gmail.com (hard-coded, single user)
    - Schedule: Sundays 22:00 UTC (= Sunday 7pm ART)
    - No AI cost; Resend free tier covers ≤3000/mo

Fail modes:
    - No active CV → log & exit(0). Nothing to summarize before a CV is up.
    - Zero scored jobs this week → send a short "no matches" email
      so silence never masks a broken pipeline.
    - Resend error → log to stderr, exit non-zero so Actions flags it.

Usage:
    python scraper/weekly_summary.py           # send
    python scraper/weekly_summary.py --dry     # print HTML, don't send
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
import json
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import supabase_client

RECIPIENT = "eugeniogdelatorre@gmail.com"
# Resend requires the "From" address to use a verified domain. Until
# Eugenio verifies a custom domain, Resend provides onboarding@resend.dev
# which works out-of-the-box for accounts sending to themselves.
FROM_ADDR = os.environ.get("RESEND_FROM") or "Job Agent <onboarding@resend.dev>"
TOP_N = 10
LOOKBACK_DAYS = 7


def fetch_top_jobs(client, active_resume_id: str):
    """Return up to TOP_N job_scores rows joined with their job, newest first by match_score.

    Audit M19: previously fetched ``TOP_N * 3`` candidates and filtered
    ``is_active`` + ``gate_failed`` in Python. When inactive/gated rows
    clustered at the top of the score distribution the email came up
    short — e.g. 30 candidates fetched, 28 dropped, only 2 made the
    digest. Push both filters into SQL via the inner join on ``jobs``
    so the ``.limit(TOP_N)`` budget actually buys ``TOP_N`` rows.
    """
    if client is None:
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).isoformat()
    try:
        resp = (
            client.table("job_scores")
            .select(
                "match_score, strengths, gaps, verdict_one_liner, scored_at, "
                # !inner so the parent (job_scores) is filtered by
                # embed columns instead of nullifying its embed slot.
                "jobs!inner(id, title, company, apply_url, source_url, source, "
                "function_category, vertical, seniority, remote_status, "
                "salary_min_usd, salary_max_usd, first_seen_at, is_active, "
                "score_breakdown)"
            )
            .eq("resume_id", active_resume_id)
            .gte("scored_at", cutoff)
            # Audit L5 (2026-05-20): .eq("jobs.*") embedded filters only work
            # with !inner joins (used above). If the embed is ever changed to
            # a left join, these filters would silently return all rows instead
            # of filtering. Keep the !inner on the select above in sync.
            .eq("jobs.is_active", True)
            .is_("jobs.score_breakdown->>gate_failed", "null")
            .order("match_score", desc=True)
            .limit(TOP_N)
            .execute()
        )
        rows = getattr(resp, "data", []) or []
    except Exception as e:
        print(f"  [summary] fetch failed: {e}", file=sys.stderr)
        return []

    # Defensive: filter any row whose embedded job is missing (shouldn't
    # happen with !inner, but better than crashing the email render).
    return [r for r in rows if r.get("jobs")]


def _fmt_salary(mn, mx) -> str:
    def one(n):
        n = int(n)
        return f"${n // 1000}k" if n >= 1000 else f"${n}"
    if mn and mx and mn != mx:
        return f"{one(mn)}–{one(mx)}"
    if mn or mx:
        return one(mn or mx)
    return ""


def _badge_color(score: int) -> tuple[str, str]:
    """Return (bg, fg) hex pair matching MatchBadge colors."""
    if score >= 80:
        return ("#dcfce7", "#166534")  # green
    if score >= 60:
        return ("#dbeafe", "#1e40af")  # blue
    if score >= 40:
        return ("#fef9c3", "#854d0e")  # yellow
    return ("#fee2e2", "#991b1b")       # red


def render_html(rows: list[dict], web_base: str) -> str:
    """Build the HTML email. Minimal table-based layout for gmail compatibility."""
    if not rows:
        return (
            '<div style="font-family:system-ui,sans-serif;max-width:560px;margin:0 auto;padding:24px;color:#1f2937">'
            "<h2>Your weekly job roundup</h2>"
            "<p>No scored jobs in the last 7 days. Either the scraper is quiet "
            "or nothing cleared the warm threshold. Check "
            f'<a href="{escape(web_base)}/settings">/settings</a> for source health.</p>'
            "</div>"
        )

    cards = []
    for r in rows:
        job = r.get("jobs") or {}
        score = int(r.get("match_score") or 0)
        bg, fg = _badge_color(score)
        badges = []
        for key in ("function_category", "vertical", "seniority", "remote_status"):
            v = job.get(key)
            if v and v != "Unspecified":
                badges.append(
                    f'<span style="display:inline-block;background:#f3f4f6;color:#374151;'
                    f'border-radius:4px;padding:2px 8px;margin-right:4px;font-size:12px">{escape(v)}</span>'
                )
        salary = _fmt_salary(job.get("salary_min_usd"), job.get("salary_max_usd"))
        if salary:
            badges.append(
                f'<span style="display:inline-block;background:#f3f4f6;color:#374151;'
                f'border-radius:4px;padding:2px 8px;margin-right:4px;font-size:12px">{escape(salary)}</span>'
            )

        strengths = r.get("strengths") or []
        gaps = r.get("gaps") or []
        verdict = r.get("verdict_one_liner") or ""

        highlight_rows = ""
        if strengths:
            highlight_rows += (
                '<div style="color:#166534;font-size:13px;margin-top:4px">'
                f"✓ {escape(strengths[0])}</div>"
            )
        if gaps:
            highlight_rows += (
                '<div style="color:#991b1b;font-size:13px;margin-top:2px">'
                f"✗ {escape(gaps[0])}</div>"
            )
        if verdict:
            highlight_rows += (
                '<div style="color:#6b7280;font-size:12px;font-style:italic;margin-top:4px">'
                f"{escape(verdict)}</div>"
            )

        apply_href = job.get("apply_url") or job.get("source_url") or ""
        title = escape(job.get("title") or "")
        company = escape(job.get("company") or "")

        cards.append(
            f"""
<table role="presentation" width="100%" style="margin-bottom:14px;border:1px solid #e5e7eb;border-radius:8px;border-collapse:separate">
  <tr><td style="padding:14px">
    <table role="presentation" width="100%">
      <tr>
        <td style="vertical-align:top">
          <div style="font-size:15px;font-weight:600;color:#111827">{title}</div>
          <div style="font-size:13px;color:#6b7280;margin-top:2px">{company}</div>
        </td>
        <td style="vertical-align:top;text-align:right;padding-left:12px;white-space:nowrap">
          <span style="display:inline-block;background:{bg};color:{fg};border-radius:999px;padding:3px 10px;font-size:13px;font-weight:600">{score}%</span>
        </td>
      </tr>
    </table>
    <div style="margin-top:8px">{''.join(badges)}</div>
    {highlight_rows}
    {f'<div style="margin-top:10px"><a href="{escape(apply_href)}" style="display:inline-block;background:#111827;color:#ffffff;text-decoration:none;padding:6px 12px;border-radius:6px;font-size:13px">Apply →</a></div>' if apply_href else ''}
  </td></tr>
</table>
"""
        )

    return f"""
<div style="font-family:system-ui,sans-serif;max-width:620px;margin:0 auto;padding:24px;color:#1f2937;background:#ffffff">
  <h2 style="margin:0 0 4px">Your weekly job roundup</h2>
  <p style="margin:0 0 18px;color:#6b7280;font-size:13px">
    Top {len(rows)} matches from the last {LOOKBACK_DAYS} days · ranked by AI match score
  </p>
  {''.join(cards)}
  <p style="margin-top:24px;color:#9ca3af;font-size:12px">
    Open the dashboard: <a href="{escape(web_base)}" style="color:#6b7280">{escape(web_base)}</a>
  </p>
</div>
"""


def send_via_resend(api_key: str, html: str, subject: str) -> bool:
    """POST to Resend. Returns True on 2xx."""
    payload = {
        "from": FROM_ADDR,
        "to": [RECIPIENT],
        "subject": subject,
        "html": html,
    }
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Cloudflare (in front of api.resend.com) 1010-bans the default
            # ``Python-urllib/3.x`` UA. A generic UA passes through fine.
            "User-Agent": "job-search-agent-v3/1.0",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"  [resend] {resp.status} {resp.reason}")
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        print(f"  [resend] HTTP {e.code}: {body}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  [resend] send failed: {e}", file=sys.stderr)
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="print HTML, don't send")
    args = ap.parse_args()

    client = supabase_client.get_client()
    if client is None:
        print("  [summary] no supabase client — aborting", file=sys.stderr)
        return 1

    # Audit C2 (2026-05-19): scope the resume lookup by user_id so the
    # weekly digest is always built from the owner's CV. Pre-fix this
    # ran a global SELECT and could have picked any user's active row;
    # combined with the hardcoded RECIPIENT below that meant the digest
    # could be built against Federico/Ana's CV but still shipped to
    # Eugenio. Fail-closed if the env var is unset.
    owner_id = supabase_client.get_pipeline_owner_user_id()
    if not owner_id:
        print(
            "  [fatal] PIPELINE_OWNER_USER_ID missing — refusing to run. "
            "Set it to the Supabase auth.users.id of the pipeline owner "
            "in GitHub repo Settings → Secrets and variables → Actions. "
            "(See REVIEW.md C2.)",
            file=sys.stderr,
        )
        return 2

    # Find active resume (scoped to the owner)
    try:
        resp = (
            client.table("resumes")
            .select("id")
            .eq("user_id", owner_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        active = (getattr(resp, "data", []) or [])
    except Exception as e:
        print(f"  [summary] resumes lookup failed: {e}", file=sys.stderr)
        return 1
    if not active:
        print("  [summary] no active CV — skipping this week")
        return 0
    active_resume_id = active[0]["id"]

    rows = fetch_top_jobs(client, active_resume_id)
    print(f"  [summary] rendering {len(rows)} row(s) for {active_resume_id}")

    web_base = os.environ.get("WEB_BASE_URL", "https://job-search-agent-v3.vercel.app")
    html = render_html(rows, web_base)
    subject = (
        f"Job agent · top {len(rows)} this week"
        if rows
        else "Job agent · no matches this week"
    )

    if args.dry:
        print(html)
        return 0

    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        print("  [summary] RESEND_API_KEY missing", file=sys.stderr)
        return 1

    ok = send_via_resend(api_key, html, subject)
    if not ok:
        return 1

    # Log spend row even though cost is $0 — makes the ledger complete.
    try:
        client.table("spend_tracking").insert(
            {
                "operation": "weekly_summary",
                "model": "resend",
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0,
                "notes": f"top {len(rows)} jobs · {LOOKBACK_DAYS}d lookback",
            }
        ).execute()
    except Exception as e:
        print(f"  [summary] spend log failed (non-fatal): {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
