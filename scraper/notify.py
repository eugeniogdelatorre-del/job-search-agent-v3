"""Send a failure-notification email via Resend.

Used by every scheduled GitHub Actions workflow on `if: failure()`. Without
this, a scrape / classify / batch failure is silent until the operator
checks the dashboard the next morning and notices stale data — audit H5.

Reads from env:
  RESEND_API_KEY  — required; if missing, prints a warning and exits 0
                    so the notify step never adds noise on top of a real
                    failure.
  WORKFLOW_NAME   — `${{ github.workflow }}` (e.g. "scrape", "classify")
  RUN_URL         — direct link to the failed run
  STATUS_DETAIL   — optional free-text appended to the email body

Fail-soft everywhere: this script must never raise. If we can't tell the
operator there was a failure, we'd rather log to stderr and exit clean
than make the workflow look like it failed twice.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


ALERT_RECIPIENT = "eugeniogdelatorre@gmail.com"
ALERT_FROM = os.environ.get("RESEND_FROM") or "Job Agent <onboarding@resend.dev>"


def _build_payload(name: str, url: str, detail: str) -> bytes:
    detail_html = f"<p>{detail}</p>" if detail else ""
    html = (
        '<div style="font-family:system-ui,sans-serif;padding:20px;max-width:560px">'
        f"<h2>Workflow failed: {name}</h2>"
        f"{detail_html}"
        f'<p><a href="{url}">Open the failed run</a></p>'
        "<p style=\"color:#666;font-size:12px\">"
        "Failure notifications come from <code>scraper/notify.py</code>; "
        "to mute, remove the <code>notify_on_failure</code> job from the "
        "workflow YAML."
        "</p>"
        "</div>"
    )
    payload = {
        "from": ALERT_FROM,
        "to": [ALERT_RECIPIENT],
        "subject": f"[job-agent] {name} FAILED",
        "html": html,
    }
    return json.dumps(payload).encode("utf-8")


def main() -> int:
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        # Use GitHub Actions log-level annotation so it shows up as a
        # warning rather than a hard failure.
        print(
            "::warning::RESEND_API_KEY not set; skipping failure email",
            file=sys.stderr,
        )
        return 0

    name = (os.environ.get("WORKFLOW_NAME") or "unknown").strip() or "unknown"
    url = (os.environ.get("RUN_URL") or "").strip()
    detail = (os.environ.get("STATUS_DETAIL") or "").strip()

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=_build_payload(name, url, detail),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Cloudflare in front of api.resend.com 1010-bans the default
            # Python-urllib UA. Same workaround as scraper/budget.py.
            "User-Agent": "job-search-agent-v3/1.0",
            "Accept": "application/json",
        },
        method="POST",
    )
    # Audit L2 (2026-05-14): retry transient failures. The previous
    # version sent once and bailed; during a Resend brownout we'd lose
    # the failure notification for the whole day. Two retries with 5s
    # backoff catch the common case (a 503 from Cloudflare in front of
    # api.resend.com) without blocking the workflow for long.
    import time
    MAX_ATTEMPTS = 3
    BACKOFF_SECONDS = 5
    last_err: str = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                print(f"[notify] sent: HTTP {resp.status} (attempt {attempt})")
            return 0
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read()[:300].decode("utf-8", errors="replace")
            except Exception:
                pass
            last_err = f"HTTP {e.code}: {body!r}"
            # 4xx (other than 429) are not transient — don't retry.
            if 400 <= e.code < 500 and e.code != 429:
                break
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
        if attempt < MAX_ATTEMPTS:
            time.sleep(BACKOFF_SECONDS)
    print(f"::warning::[notify] gave up after {MAX_ATTEMPTS} attempts: {last_err}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
