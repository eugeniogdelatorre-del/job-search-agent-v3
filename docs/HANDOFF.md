# HANDOFF

Self-contained context for another chat (or future-you) to maintain,
debug, and extend `job-search-agent-v3` without re-reading the full
plan. Read this top to bottom once.

Owner: Eugenio (single-user install, Buenos Aires).
Status: Phases 0–9 complete. Daily driver since 2026-04.

---

## 1. One-paragraph overview

Personal Web3 job aggregator. A Python scraper (GitHub Actions) hits
~268 sources daily, dedupes, rule-scores, and persists to Supabase.
A nightly Batch-API pipeline (classify → geo_filter → cv_score)
classifies new jobs, drops location-ineligible roles, and scores every
"warm" survivor against the active CV using Claude Haiku 4.5 with
prompt caching. A small Next.js 14 dashboard on Vercel renders the
results, lets Eugenio track applications on a kanban, and export
filtered CSVs. A weekly email digest ships Sunday 19:00 ART. Hard
budget cap: **$8/mo**. Projected run rate: **~$0.22/mo**.

## 2. Where things live

| Surface | URL / Location |
|---|---|
| GitHub repo | https://github.com/eugeniogdelatorre-del/job-search-agent-v3 |
| Production | https://job-search-agent-v3.vercel.app |
| Vercel project ID | `prj_ZmPFMkXDFRtP29sLb5xfBka47zAz` (team `eugeniogdelatorre-7277s-projects`) |
| Supabase project | `nqevtnhryjnlbzmiojyb` (São Paulo, free tier) |
| Resend API key label | `job-search-agent-v3` |
| CI | GitHub Actions (public repo → unlimited minutes) |

Repo layout:

```
scraper/              Python 3.12 — runs only in GitHub Actions
  scrape.py             daily 04:00 UTC — all sources
  classify.py           daily 05:00 UTC — new jobs (function/vertical/seniority/remote)
  geo_filter.py         daily 06:00 UTC — AI location-eligibility check
  cv_score.py           daily 07:00 UTC — warm + geo-passed jobs vs. active CV
  weekly_summary.py     Sun 22:00 UTC — top 10 by match%
  retention.py          called inside scrape.py; 60d hard delete + 30d auto-stale
  stale_apps.py         called from retention.py; Applied → Stale at 30d untouched
  _anthropic_batch.py   shared Anthropic SDK client + Batch poll + JSON parse
  score.py              rule-based scorer + hard-coded DEFAULT_CONFIG
  budget.py             $8 cap + Resend alert on trip
  supabase_client.py    service-role client
  parsers/              one module per source type
  sources.json          source list (edit to add/remove)

web/                  Next.js 14 App Router — deploys to Vercel
  src/app/              routes (Today, /week, /archive, /apply,
                        /resume, /settings, /login, /api/*)
  src/components/       shadcn/ui-based components, KanbanBoard,
                        SpendChart, etc.
  src/lib/              jobs-query, filters, format, supabase/
  middleware.ts         auth gate — getUser() not getSession()

docs/
  JOB_SEARCH_AGENT_V3_PLAN.md   source of truth (the locked spec)
  RUNBOOK.md                    operational recipes
  COST_MATH.md                  spend projection + pricing reference
  HANDOFF.md                    this file
```

## 3. Stack

- **Scraper:** Python 3.12 — `requests`, `beautifulsoup4`, `supabase`, `anthropic`
- **Web:** Next.js 14 App Router, React 18, TypeScript, Tailwind v3
  (NOT v4 — shadcn CLI would break it), shadcn/ui (hand-written
  components, no CLI), `@dnd-kit` for kanban
- **PDF parsing:** `unpdf` (serverless pdfjs; `pdf-parse` fails on
  Vercel because it needs browser globals)
- **Database + Auth + Storage:** Supabase
- **Scheduling:** GitHub Actions cron
- **AI:** Claude Haiku 4.5 via Anthropic **Batch** API with prompt
  caching (50% off base price + 0.1× for cache reads)
- **Email:** Resend (free tier, 3000/mo)
- **Host:** Vercel (free tier)

## 4. Schedules (timing)

All times below are UTC; Buenos Aires is UTC−3.

| Workflow | Cron (UTC) | BA time | Purpose |
|---|---|---|---|
| `scrape.yml` | `0 4 * * *` | 01:00 daily | Fetch + parse + dedup + rule-score + retention sweep |
| `classify.yml` | `0 5 * * *` | 02:00 daily | Batch-classify new jobs (function / vertical / seniority / remote / salary) |
| `geo_filter.yml` | `0 6 * * *` | 03:00 daily | AI location-eligibility check vs candidate's city |
| `cv_score.yml` | `0 7 * * *` | 04:00 daily | Batch-score every warm + geo-passed job (rule score ≥ 40) against the active CV |
| `weekly_summary.yml` | `0 22 * * 0` | Sun 19:00 | Top-10 match-% email via Resend |
| `pipeline.yml` | manual | — | One-click chain of scrape → classify → geo_filter → cv_score |

Each workflow is idempotent and has `workflow_dispatch` for manual
runs. Cap trip raises `BudgetExceeded` and fires a Resend alert email
(fail-soft — alert failures don't block the exception).

## 5. Environment secrets & variables

### GitHub Actions

**Secrets** (Settings → Secrets and variables → Actions → Secrets):

| Name | Used by |
|---|---|
| `SUPABASE_URL` | all workflows |
| `SUPABASE_SERVICE_KEY` | all workflows |
| `ANTHROPIC_API_KEY` | classify, geo_filter, cv_score |
| `RESEND_API_KEY` | weekly_summary, + cap-trip alert in classify/cv_score |
| `WEB3_CAREER_API_KEY` | scrape (optional) — when set, `web3career` parser uses the official API (~27k+ listings); when missing, it falls back to HTML scrape of the homepage |

**Variables** (same page → Variables tab):

| Name | Value |
|---|---|
| `WEB_BASE_URL` | `https://job-search-agent-v3.vercel.app` (no trailing slash) |
| `CANDIDATE_LOCATION` | **optional** — only set this to override the CV-based extraction (geo_filter normally asks Haiku to read the active CV) |

### Vercel (all environments unless noted)

| Name | Scope |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Preview + Production |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Preview + Production |
| `SUPABASE_SERVICE_KEY` | Production only (server actions) |

## 6. Views

| Path | What it does |
|---|---|
| `/` | **Today** — jobs seen in last 24h, default sort match% desc |
| `/week` | Top 100 by match% over last 7 days |
| `/archive` | Full filtered table, last 60 days, 50/page |
| `/apply` | Kanban — Saved / Applied / Interview / Offer / Rejected / Stale. Drag-drop, notes, optimistic UI. Stale is auto-populated by `stale_apps.run` (Applied + 30d untouched); user can drag back. |
| `/resume` | Upload + activate CV (PDF only, keeps last 5) |
| `/settings` | MTD spend chart, per-source health, account info |

Filter state lives in URL search params — sharing and back-button
just work. Gate-rejected jobs are hidden (`score_breakdown->>gate_failed IS NULL`).

## 7. How data flows

```
sources.json
    │
    ▼
scrape.py (every 4h)
    │
    ├─ parsers/*           fetch + normalize
    ├─ dedup on (source, external_id)
    ├─ score.py            rule score + gate
    └─ retention.py        is_active=false after 7d, delete after 60d
    │
    ▼
jobs table  (Supabase)
    │
    ├─ classify.py (daily 05:00 UTC)
    │    └─ Batch API — Haiku 4.5
    │       adds function / vertical / seniority / remote / salary
    │
    ├─ geo_filter.py (daily 06:00 UTC)
    │    └─ Batch API — Haiku 4.5
    │       sets geo_filtered=true; is_active=false on geo-rejects
    │
    └─ cv_score.py (daily 07:00 UTC)
         └─ Batch API + prompt caching
            writes job_scores rows with match_score (warm + geo-passed only)
    │
    ▼
web/ dashboard
    │
    ├─ /today, /week, /archive    → queryJobs()
    ├─ /apply                     → applications (snapshot fields)
    ├─ /resume                    → resumes (PDF → text via unpdf)
    └─ /settings                  → spend_tracking, source_runs
    │
    ▼
weekly_summary.py (Sun 22:00 UTC)
    └─ Resend → eugeniogdelatorre@gmail.com
```

Key design choices worth knowing:

- **Snapshot fields on `applications`** — title/company/url/etc. are
  copied onto the kanban row so applications survive the 60-day job
  retention sweep even if the underlying `job_id` goes NULL.
- **Gate-rejected jobs are kept**, not dropped, so you can see what's
  filtering and why (`score_breakdown.gate_failed`).
- **Warm threshold** gates CV scoring at `score_total ≥ 40`. Lowered
  from 60 to 40 to score the majority of visible jobs (~444 vs 29).
  cv_score.py also requires `geo_filtered=true` so it never scores
  jobs that failed the location check.
- **Prompt caching on CV scoring**: the CV is in the system block
  with `cache_control: ephemeral`, so per-job cost is ~3500 cached
  (0.1× base) + 600 fresh input + 250 output.

## 8. Daily usage (what "using it" looks like)

1. **Morning check** (~5 min): open `/` — triage new matches.
   - Click through interesting ones.
   - Hit "Save" to drop into the kanban `Saved` column.
2. **Applying**: on `/apply`, drag from Saved → Applied. `applied_at`
   auto-fills the first time a card lands in Applied.
3. **Weekly recap**: Sun evening email lands in inbox at 19:00 ART.
   Top 10 by match% for the past 7 days.
4. **Tuning**: if too many junk matches surface, edit `DEFAULT_CONFIG`
   in `scraper/score.py` (gates / weights / thresholds), commit, push.
   Next scrape re-scores freshly-seen jobs. To re-score existing rows
   immediately: manual dispatch `scrape.yml`.
5. **Spend watch**: `/settings` — MTD chart. Cap is $8. Expected spend
   is pennies; anything > $1 means something's looping.

## 9. Common operations

Full detail in `docs/RUNBOOK.md`. Short index:

| Task | Where |
|---|---|
| Add / remove a source | Edit `scraper/sources.json`, open PR |
| Debug a dead scraper | `/settings` → source health, then manual `scrape.yml` with `--sources <name>` |
| Rotate API keys | RUNBOOK §"Rotate API keys" — both GH + Vercel as applicable |
| Budget cap tripped | RUNBOOK §"Budget cap tripped" — SQL delete rows or raise cap |
| Weekly summary missing | Check Actions; the usual causes are missing `RESEND_API_KEY` or no active CV |
| Re-score existing rows after editing score.py | Manual dispatch `scrape.yml` |
| Change candidate location for geo_filter | Set repo variable `CANDIDATE_LOCATION`; UPDATE jobs SET geo_filtered=false to re-evaluate existing rows |

## 10. Cost model (summary — full math in `docs/COST_MATH.md`)

At ~100 active jobs, ~300 new/mo, ~180 warm/mo:

| Operation | Monthly |
|---|---|
| Classification | ~$0.06 |
| CV scoring | ~$0.16 |
| Weekly summary | $0 |
| **Total AI** | **~$0.22/mo** |

Linear to 5× volume: ~$1.10/mo. Cap at $8 exists to catch runaway
loops, not expected usage. $8 sits under the $10 ceiling so retries
between trip and alert email fit in budget.

Knobs when/if costs climb (in order of effectiveness):
1. Raise the warm threshold in `cv_score.py` (default 40 → try 50/60)
2. Shrink description truncation in prompts (§4.1 uses 2000, §4.2 uses 3000 chars)
3. Drop low-match aggregator sources (tier 1)
4. Tighten gates in `score.py` to reject more rows pre-AI

## 11. Known gotchas / things that bit us

- **`pdf-parse` pulls in `pdfjs-dist`** which needs DOMMatrix /
  Promise.withResolvers — not in Vercel's Node runtime. Use `unpdf`
  instead. **Do not reintroduce pdf-parse.**
- **`api.resend.com` is behind Cloudflare** — Python's default
  `urllib` User-Agent (`Python-urllib/3.12`) gets 1010-banned at the
  edge (HTTP 403, "error code: 1010"). Every request to Resend must
  set a custom `User-Agent` header. Applied in `weekly_summary.py`
  and `budget.py`; keep it in any new Resend caller.
- **Tailwind v3, not v4.** The shadcn CLI defaults to v4 presets that
  don't round-trip through our v3 setup; components are hand-written
  on purpose. If you run `shadcn-ui add`, inspect the output.
- **React `no-unescaped-entities`** — Vercel's lint blocks straight
  `"` in JSX text. Use `&quot;` or wrap in `{'...'}`.
- **TS2802 iteration** — Map/URLSearchParams spread can trip the TS
  target. Use `Array.from(map.entries())` and `sp.forEach(...)`
  instead of `[...map.entries()]` / `for...of sp.entries()`.
- **The `.gitignore` had `lib/`** (Python venv pattern) which silently
  masked `web/src/lib/`. Fixed in `bee16c2`. Don't re-add it; use
  `.venv/` and `venv/` instead.
- **`NEXT_PUBLIC_SUPABASE_ANON_KEY`** is public by design but
  `SUPABASE_SERVICE_KEY` is not — never expose it client-side. Server
  routes that need write access (e.g. `/api/cv/*`, `/api/applications`)
  use the service role.
- **Source tier is stored per-job** at insert time. Changing a
  source's tier only affects rows inserted after the edit.

## 12. Architectural invariants (don't break these)

- Scraper runs **only** in GitHub Actions. Never port it to Vercel —
  the 300s Fluid Compute limit and stateless model don't match.
- Web is **read-mostly** with narrow write APIs (`/api/applications`,
  `/api/cv/*`). Don't add direct DB writes from client components.
- Every new Anthropic call goes through **Batch + prompt caching**
  unless you have a specific reason. The cost model assumes it.
- Budget cap check (`budget.assert_under_budget`) gates every AI
  workflow. Pass an `operation` label so the alert email names it.
- Retention is 60 days on jobs. New long-lived user data must carry
  snapshot fields or live in its own table.
- Scoring config is a **partial override** of `DEFAULT_CONFIG` in
  `scraper/score.py`. The saved jsonb is deep-merged. The UI shows
  the override only, not the merged result.

## 13. Extending the system

| Change | Touch points |
|---|---|
| New source | `scraper/sources.json`, maybe a new `parsers/*.py` |
| New filter on the web UI | `src/lib/filters.ts` (parse + serialize), `FilterBar`, and `jobs-query` |
| New scorer signal | `DEFAULT_CONFIG` in `score.py`, optionally expose a UI field |
| New AI task | New `scraper/<task>.py`, new workflow, must call `budget.assert_under_budget(client, operation="…")` |
| New table | Add a migration in Supabase, update `src/types/db.ts`, add snapshot fields if it outlives 60 days |

## 14. Debugging checklist (copy-paste into the next chat)

If the next chat inherits a broken-something, run these first:

1. **GitHub Actions tab** — which workflow failed? open latest run.
2. **`/settings` source health** — is a parser dead?
3. **Supabase SQL**:
   ```sql
   -- MTD spend
   select operation, sum(cost_usd) from spend_tracking
   where run_at >= date_trunc('month', now()) group by 1 order by 2 desc;

   -- Latest scrape result per source
   select * from source_runs order by run_at desc limit 20;

   -- Unscored warm jobs backlog
   select count(*) from jobs
   where score_total >= 60 and score_breakdown->>'gate_failed' is null
   and id not in (select job_id from resume_scores where resume_id = (select id from resumes where is_active));
   ```
4. **Vercel deployment logs** — production only; preview builds don't
   run workflows.
5. **Search `docs/RUNBOOK.md`** — the most-likely-cause is usually
   written down.

## 15. Recent commits (context for the next chat)

| SHA | What |
|---|---|
| `32abd65` | fix(resend): User-Agent to bypass Cloudflare 1010 |
| `daa1fcc` | Phase 9 — polish + docs (RUNBOOK, COST_MATH, README refresh, budget alert email) |
| `62597db` | Phase 8 — /tune, /settings, /api/export, weekly_summary (deploy failed, superseded by daa1fcc) |
| `e8fd51b` | Phase 7 — kanban apply tracker |
| `ee0f9b2` | fix(cv-upload): swap pdf-parse → unpdf |
| `0ee9e61` | Phase 6 — CV upload + Batch-API CV scoring with prompt caching |

## 16. Related docs

- [`JOB_SEARCH_AGENT_V3_PLAN.md`](../JOB_SEARCH_AGENT_V3_PLAN.md) —
  the locked spec the repo was built against. Authoritative for
  design decisions and phase boundaries.
- [`docs/RUNBOOK.md`](RUNBOOK.md) — operational recipes.
- [`docs/COST_MATH.md`](COST_MATH.md) — spend math.
- [`README.md`](../README.md) — public-facing tl;dr.

---

Last updated: 2026-04-24 (commit `32abd65`). Bump this line when you
make a meaningful change.
