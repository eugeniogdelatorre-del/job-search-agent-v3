# job-search-agent-v3

Personal Web3 job-search automation. Scrapes ~30 sources every 4 hours, deduplicates, rule-scores, then runs a nightly AI classification + CV-match pipeline on the Anthropic Batch API. Results land in a small Next.js dashboard with a kanban apply tracker and a weekly email digest.

**Status:** Under active construction. Phase 0 — infra bootstrap.

## Stack

- **Scraper:** Python 3.12 — `requests`, `beautifulsoup4`, `pdfplumber`, `supabase`, `anthropic`
- **Web:** Next.js 14 App Router, TypeScript, Tailwind, shadcn/ui
- **Database + Auth + Storage:** Supabase (São Paulo region, free tier)
- **Scheduling:** GitHub Actions (public repo = unlimited minutes)
- **AI:** Claude Haiku 4.5 via Batch API with prompt caching
- **Email:** Resend (free tier, weekly summary + spend alerts)
- **Host:** Vercel (free tier)

## Cost

Hard cap: **$8/mo** enforced in code. Realistic projection: ~$0.22/mo. Budget ceiling: $10/mo.

## Project status

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

## License

MIT — see [LICENSE](LICENSE).
