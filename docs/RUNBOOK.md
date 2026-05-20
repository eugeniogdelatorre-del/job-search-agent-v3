# RUNBOOK

Operational recipes. Owner: Eugenio. Single-user install.

Related docs:
- `JOB_SEARCH_AGENT_V3_PLAN.md` — architecture + build plan (source of truth)
- `docs/COST_MATH.md` — actual spend breakdown

---

## Layout recap

```
scraper/        Python 3.12 — GitHub Actions only
  scrape.py       every 4h (matrix: group 1 + group 2)
  classify.py     06:00 UTC daily
  cv_score.py     07:00 UTC daily
  weekly_summary  22:00 UTC Sundays (Sun 19:00 ART)
web/            Next.js 14 App Router — Vercel
```

Supabase project: `nqevtnhryjnlbzmiojyb` (São Paulo, free tier).

---

## Add a new source

1. Edit `scraper/sources.json`. Each entry:
   ```json
   {
     "name": "some-company",
     "url": "https://boards.greenhouse.io/somecompany",
     "parser": "greenhouse",   // or lever / ashby / workday / cryptojobslist / web3career / weworkremotely / generic
     "tier": 3,                 // 1 broad board, 2 web3 aggregator, 3 direct ATS
     "group": 1                 // 1 or 2 (cron matrix splits these)
   }
   ```
2. Parser options:
   - `greenhouse`, `lever`, `ashby` — JSON APIs, most reliable
   - `workday` — heavier but handles customer portals
   - `cryptojobslist`, `web3career` — specific aggregators
   - `weworkremotely` — includes v2's unmasher for squashed titles
   - `generic` — last-resort HTML parser
3. Open a PR. The next scrape cycle (every 4h) picks it up.
4. Confirm the run in `/settings` → source health. Source tier is stored
   per-job; changes only apply to jobs inserted after the edit.

## Debug a dead scraper

1. `/settings` → source health table surfaces failures first. Grab the
   error message.
2. Manual re-run: GitHub Actions → `scrape.yml` → "Run workflow" with
   the matching group.
3. Common causes:
   - 404 — URL moved; fix in `sources.json`
   - HTML changed — parser drifted; inspect raw response with a scratch
     script (see below)
   - Rate-limit — back off by dropping that source's frequency or cache
     fetches
4. Local smoke test:
   ```bash
   cd scraper
   pip install -r requirements.txt
   SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python scrape.py --group 1 --sources <name>
   ```
   (scrape.py supports `--sources <comma-separated-names>` as an ad-hoc filter.)

## Rotate API keys

| Key | Where it lives | When to rotate |
|---|---|---|
| `SUPABASE_SERVICE_KEY` | GitHub Actions secret + Vercel Production env | If leaked or quarterly |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Vercel (all envs) | Same |
| `ANTHROPIC_API_KEY` | GitHub Actions secret | If leaked |
| `RESEND_API_KEY` | GitHub Actions + Vercel Production | If leaked |

Rotation recipe:
1. Create the new key in the provider's dashboard
2. Update the secret in **both** GitHub and Vercel (where applicable)
3. Kick a manual workflow run + redeploy to confirm
4. Revoke the old key in the provider dashboard

## Budget cap tripped

Symptoms:
- GitHub Actions run fails with `BudgetExceeded`
- Inbox has "Spend cap tripped" email from Resend

Recovery:
1. Check `/settings` SpendChart to see which operation is eating budget
2. Inspect `spend_tracking` in the Supabase SQL editor:
   ```sql
   select run_at, operation, model, cost_usd, notes
   from spend_tracking
   where run_at >= date_trunc('month', now())
   order by run_at desc;
   ```
3. Root cause: usually a classification/CV-scoring retry loop. Confirm
   the latest Actions run failure reason.
4. The cap resets on the 1st of next UTC month. To resume sooner:
   - pragmatic: `delete from spend_tracking where run_at >= '<today>';`
     (removes logs, lets the MTD sum drop back under the cap)
   - or raise `BUDGET_CAP_USD` in `scraper/budget.py` if you know why
     it tripped and want to continue.

## Retention sweep

Runs inside each scrape cycle via `scraper/retention.py`:
- `is_active = false` for jobs with `last_seen_at` > 30 days ago
- hard delete for jobs with `first_seen_at` > 60 days ago

Applications (kanban) carry snapshot fields — they survive the delete
even if `job_id` becomes NULL.

## Scoring config changes

The rule-based scorer's config (gates + dimension weights) is hard-coded
in `DEFAULT_CONFIG` in `scraper/score.py`. There's no DB merge or `/tune`
UI anymore — the AI scorer (`cv_score.py`) is the primary ranker, and
the rule-based score now serves only as a budget gate (`score_total < 40`
means the row is skipped by `cv_score.py`).

To change weights / gates / thresholds: edit `scraper/score.py`,
commit, push. Next scrape re-scores anything it touches; to apply
immediately to existing rows trigger `scrape.yml` via manual dispatch.

## Changing candidate location (geo_filter)

Default behavior: `geo_filter.py` asks Haiku to extract the candidate's
city/country from the **active CV** at the start of every run. So just
upload + activate a new CV on `/resume` and the next geo_filter run
picks up the new location automatically.

If you need to force a specific string (e.g. while testing, or if the
AI extraction is wrong), set the `CANDIDATE_LOCATION` repo variable
(Settings → Secrets and variables → Actions → Variables) to e.g.
`Buenos Aires, Argentina`. Delete the variable to go back to CV-based
extraction.

Already-filtered rows aren't re-checked. To re-evaluate every row
after the candidate location changes, run:

```sql
UPDATE jobs SET geo_filtered = false WHERE is_active = true;
```

then trigger `geo_filter.yml` manually.

## Weekly summary missing

1. Check Actions → `weekly_summary.yml` last run.
2. If `no active CV` in the log: upload + activate a CV on `/resume`.
3. If `no scored jobs`: normal if scraper was quiet all week or the
   warm threshold wasn't cleared. Inspect `/week`.
4. If Resend HTTP 403: verify `RESEND_API_KEY` is set and the sender
   domain is authorized. Default uses `onboarding@resend.dev` which
   works without domain setup.

## Local development

```bash
# Scraper
cd scraper && pip install -r requirements.txt
# needs SUPABASE_URL, SUPABASE_SERVICE_KEY in env or .env

# Web
cd web && npm install && npm run dev
# expects web/.env.local with NEXT_PUBLIC_SUPABASE_URL and
# NEXT_PUBLIC_SUPABASE_ANON_KEY + SUPABASE_SERVICE_KEY
```
