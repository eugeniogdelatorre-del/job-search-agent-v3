# job-search-agent-v3

Personal Web3 job-search automation. Scrapes ~268 sources daily, deduplicates, rule-scores, then runs an AI classification + geo-filter + CV-match pipeline on the Anthropic Batch API. Results land in a small Next.js dashboard with a kanban apply tracker and a weekly email digest.

**Status:** Phases 0–9 complete. Daily driver for a single user (Eugenio).

## Stack

- **Scraper:** Python 3.12 — `requests`, `beautifulsoup4`, `supabase`, `anthropic`
- **Web:** Next.js 14 App Router, TypeScript, Tailwind, shadcn/ui, `@dnd-kit`
- **Database + Auth + Storage:** Supabase (São Paulo region, free tier)
- **PDF parsing:** `unpdf` (serverless-friendly pdfjs build)
- **Scheduling:** GitHub Actions (public repo = unlimited minutes)
- **AI:** Claude Haiku 4.5 via Batch API with prompt caching
- **Email:** Resend (free tier, weekly summary + spend alerts)
- **Host:** Vercel (free tier)

## Views

| Path | Purpose |
|---|---|
| `/` | Today — last 24h, default sort by match% |
| `/week` | Top 100 by match% from the last 7 days |
| `/archive` | Full filtered table, last 60d, paginated 50/page |
| `/apply` | Kanban — Saved / Applied / Interview / Offer / Rejected |
| `/resume` | Upload + activate CV (PDF only, last 5 kept) |
| `/settings` | MTD spend chart, per-source health, account info |

## Cost

Hard cap: **$30/mo** enforced in code (Resend alert email on trip), with per-stage sub-caps `classify $5 / geo_filter $5 / cv_score $20`. Projected ~$0.22/mo at current volumes; the headroom absorbs CV-swap backlog drains and one-off remediation runs. See [`docs/COST_MATH.md`](docs/COST_MATH.md).

## Architecture

See [`JOB_SEARCH_AGENT_V3_PLAN.md`](JOB_SEARCH_AGENT_V3_PLAN.md) — the spec the repo was built against. `/docs` has operational detail:

- [`docs/RUNBOOK.md`](docs/RUNBOOK.md) — add a source, debug a dead scraper, rotate keys, handle a cap trip
- [`docs/COST_MATH.md`](docs/COST_MATH.md) — projected and actual spend

## Scheduled workflows

| Workflow | Cron (UTC) | Purpose |
|---|---|---|
| `scrape.yml` | `0 4 * * *` | Fetch + parse + dedup + rule-score all sources |
| `classify.yml` | `0 5 * * *` | Batch-classify new jobs (function / vertical / seniority / remote / salary) |
| `geo_filter.yml` | `0 6 * * *` | AI location-eligibility check vs candidate's city (uses `CANDIDATE_LOCATION` env var) |
| `cv_score.yml` | `0 7 * * *` | Batch-score every warm + geo-passed job against the active CV |
| `weekly_summary.yml` | `0 22 * * 0` | Sun 19:00 ART — top 10 matches by email |
| `pipeline.yml` | manual | One-click chain of all 4 stages above |

Data retention: 60 days on jobs. Applications carry snapshot fields and survive the sweep.

## License

MIT — see [LICENSE](LICENSE).
