# Job Search Agent v3: Architecture & Build Plan

**Owner:** Eugenio (Buenos Aires, UTC-3)
**Built by:** Claude Code, against this spec
**Budget ceiling:** $10/mo. Realistic projection: ~$2-3/mo.
**Status:** Greenfield. Do not migrate from v2. Seed only the source list.

---

## 0. Decisions Locked

| # | Decision | Choice |
|---|---|---|
| Q1 | Scraper code | Rewrite into `sources.py` + `parsers/` + `scrape.py`, seeded by existing `career_sources.json` from v2 repo |
| Q2 | CV scoring flow | Auto: nightly Batch API on jobs above the rule-based "warm" threshold. UI defaults to sort by AI match % |
| Q3 | Auth | Supabase Auth, magic link only, single user (Eugenio) |
| Q4 | Score output | % + up to 3 strengths + up to 3 gaps + one-liner verdict |
| Q5 | Apply tracker | Yes, v1. Saved → Applied → Interview → Offer / Rejected |
| D1 | CV format | PDF only |
| D2 | Retention | 60 days, then hard delete |
| D3 | Repo | Public from day 1. Zero secrets in repo |
| D4 | Spend cap | Hard kill at $8 month-to-date. Alert email on trip |
| D5 | Weekly summary | Yes, v1. Sundays 22:00 UTC, sent to eugeniogdelatorre@gmail.com |
| D6 | Stack | Python 3.12 + Next.js 14 App Router + TS + Tailwind + shadcn/ui + Supabase + Resend |
| D7 | UI language | English |
| D8 | Salary filter | Jobs with no explicit salary are still shown when a salary floor filter is set |

**Volume target:** ~100 active jobs in main views. Daily NEW jobs are the focus. Older jobs cycle out via 60-day retention.

---

## 1. System Architecture

```
┌────────────────────────────────────────────────────────────────┐
│  GitHub Actions  (public repo = unlimited Actions minutes)     │
│                                                                │
│  scrape.yml      every 4 hours                                 │
│    1. Run scraper across all source groups (split into 2       │
│       parallel jobs to fit free-tier 6h limit)                 │
│    2. Cross-source dedup: normalize(title + company)           │
│    3. Junk filters: drop X feeds, sidebar ads,                 │
│       run WeWorkRemotely unmasher                              │
│    4. Compute rule-based 6-dim score                           │
│    5. Upsert to Supabase jobs table (insert if new,            │
│       update last_seen_at if existing)                         │
│    6. Mark jobs not seen in 7 days as is_active = false        │
│    7. Hard-delete jobs older than 60 days                      │
│    8. Log per-source result to sources_health                  │
│                                                                │
│  classify.yml    daily at 06:00 UTC                            │
│    1. Find jobs with function_category IS NULL                 │
│    2. Submit Haiku 4.5 Batch API request (50% off)             │
│    3. Poll for completion, write back: function_category,      │
│       function_confidence, seniority, vertical, salary if      │
│       extractable, remote_status                               │
│    4. Log token counts + USD to spend_tracking                 │
│    5. Hard kill if month-to-date spend > $8                    │
│                                                                │
│  cv_score.yml    daily at 07:00 UTC                            │
│    1. Find jobs where score_total >= 60 AND no row in          │
│       job_scores for the active resume_id                      │
│    2. Submit Haiku 4.5 Batch API with prompt caching on CV     │
│    3. Write match_score, strengths, gaps, verdict to           │
│       job_scores                                               │
│    4. Log spend, kill if over budget                           │
│                                                                │
│  weekly_summary.yml    Sundays 22:00 UTC (Sun 7pm ART)         │
│    1. Pull top 10 by match_score from past 7d for active CV    │
│    2. Render HTML email with cards + apply links               │
│    3. Send via Resend to eugeniogdelatorre@gmail.com           │
│    4. Log spend (Resend free tier covers 3000/mo)              │
└────────────────────────────────┬───────────────────────────────┘
                                 ↓
┌────────────────────────────────────────────────────────────────┐
│  Supabase  (free tier, São Paulo region)                       │
│                                                                │
│  Tables                                                        │
│   • jobs              rule-scored, AI-classified               │
│   • resumes           CV text + hash, owned by user_id         │
│   • job_scores        per-resume match score                   │
│   • applications      kanban with snapshot fields              │
│   • sources_health    per-scrape diagnostics                   │
│   • spend_tracking    every AI call logged                     │
│   • scoring_config    rule-based weights, editable in /tune    │
│                                                                │
│  Auth                                                          │
│   • Magic link only (no passwords)                             │
│   • Allowed emails: eugeniogdelatorre@gmail.com only           │
│      (enforced via Supabase function or env-var check)         │
│                                                                │
│  Storage                                                       │
│   • cv-uploads bucket. RLS by owner.                           │
│   • PDF binaries stored only briefly during parse,             │
│      then deleted. Only parsed text + hash retained in DB.     │
│                                                                │
│  RLS                                                           │
│   • jobs, sources_health, scoring_config: public read          │
│   • resumes, job_scores, applications, spend_tracking:         │
│      authenticated read where user_id = auth.uid()             │
│   • All writes: service role from GitHub Actions, or           │
│      authenticated user for their own rows                     │
└────────────────────────────────┬───────────────────────────────┘
                                 ↓
┌────────────────────────────────────────────────────────────────┐
│  Vercel  (free tier): Next.js 14 App Router                    │
│                                                                │
│  Public routes                                                 │
│    /login                                                      │
│                                                                │
│  Protected routes (middleware: redirect to /login if no user)  │
│    /              Today (last 24h, sorted by match%)           │
│    /week          Last 7 days, top 100 by match%               │
│    /archive       Last 60d, full filters, paginated table      │
│    /apply         Kanban tracker                               │
│    /resume        Upload, view active, version history         │
│    /tune          Rule-based scoring config editor             │
│    /settings      Spend dashboard, source health, account      │
│                                                                │
│  API routes                                                    │
│    POST /api/cv/upload         multipart, returns resume_id    │
│    POST /api/cv/activate       body: {resume_id}               │
│    POST /api/applications      create or update kanban entry   │
│    POST /api/export            body: {filter, format}          │
│    GET  /api/spend             month-to-date spend             │
│    POST /api/tune              save scoring_config             │
└────────────────────────────────────────────────────────────────┘
```

**Key design notes**

1. **No on-demand "Score these" button.** Q2 = (a) means AI scoring runs nightly on everything above warm threshold. By morning the dashboard is pre-sorted.
2. **Rule-based score is the gatekeeper.** Anything below 60 doesn't get AI-scored. This caps cost regardless of how noisy the scrape gets.
3. **Applications carry snapshot fields** (job_title_snapshot, company_snapshot, apply_url_snapshot) so the kanban survives the 60-day job deletion. You don't lose your interview history when the posting expires.
4. **Single active resume at a time.** Multiple uploads kept (last 5), one marked `is_active`. CV scoring jobs reference the active resume_id.
5. **Spend kill switch is enforced in code,** not just monitored. The classify and cv_score steps check `spend_tracking` sum before submitting and abort with a logged warning if over $8.

---

## 2. Supabase Schema (full SQL: drop into the SQL editor)

```sql
create extension if not exists "pgcrypto";

-- 1. Jobs ------------------------------------------------------------------
create table jobs (
  id uuid primary key default gen_random_uuid(),
  dedup_key text unique not null,           -- normalize(title + company)
  title text not null,
  company text,
  location text,
  remote_status text,                       -- Remote / Hybrid / Onsite / Unspecified
  salary_min_usd integer,
  salary_max_usd integer,
  salary_source text,                       -- listed | extracted_by_ai | unknown
  description text,
  apply_url text,
  source text not null,
  source_tier integer,                      -- 1 broad board, 2 web3 aggregator, 3 direct ATS
  source_url text,
  function_category text,                   -- Community / Design / Engineering / etc
  function_confidence real,
  vertical text,                            -- DeFi / L1 / L2 / CEX / etc
  seniority text,                           -- Junior / Mid / Senior / Lead / Head
  score_total real,
  score_breakdown jsonb,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index idx_jobs_first_seen on jobs (first_seen_at desc);
create index idx_jobs_score on jobs (score_total desc nulls last);
create index idx_jobs_function on jobs (function_category);
create index idx_jobs_active on jobs (is_active) where is_active = true;
create index idx_jobs_source on jobs (source);

-- 2. Resumes ---------------------------------------------------------------
create table resumes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  filename text not null,
  parsed_text text not null,
  text_hash text not null,
  char_count integer,
  is_active boolean not null default false,
  created_at timestamptz not null default now()
);

create unique index idx_resumes_one_active_per_user
  on resumes (user_id) where is_active = true;
create index idx_resumes_user on resumes (user_id, created_at desc);

-- 3. Job scores ------------------------------------------------------------
create table job_scores (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references jobs(id) on delete cascade,
  resume_id uuid not null references resumes(id) on delete cascade,
  match_score integer not null check (match_score between 0 and 100),
  strengths text[] not null default '{}',
  gaps text[] not null default '{}',
  verdict_one_liner text,
  scored_at timestamptz not null default now(),
  unique (job_id, resume_id)
);

create index idx_job_scores_resume_score on job_scores (resume_id, match_score desc);

-- 4. Applications (kanban): snapshot fields survive job deletion ----------
create table applications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  job_id uuid references jobs(id) on delete set null,
  -- snapshot at time of save:
  job_title_snapshot text not null,
  company_snapshot text,
  apply_url_snapshot text,
  source_snapshot text,
  -- kanban state:
  status text not null default 'saved'
    check (status in ('saved','applied','interview','offer','rejected')),
  applied_at timestamptz,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index idx_applications_user_status on applications (user_id, status);

-- 5. Sources health --------------------------------------------------------
create table sources_health (
  id uuid primary key default gen_random_uuid(),
  source text not null,
  run_at timestamptz not null default now(),
  jobs_found integer not null default 0,
  success boolean not null,
  error_message text,
  duration_ms integer
);

create index idx_sources_health_source_time on sources_health (source, run_at desc);

-- 6. Spend tracking --------------------------------------------------------
create table spend_tracking (
  id uuid primary key default gen_random_uuid(),
  run_at timestamptz not null default now(),
  operation text not null,                  -- classify | cv_score | weekly_summary
  model text not null,
  input_tokens integer not null default 0,
  cached_input_tokens integer not null default 0,
  output_tokens integer not null default 0,
  cost_usd numeric(10, 6) not null,
  notes text
);

create index idx_spend_run_at on spend_tracking (run_at desc);

-- 7. Scoring config (single row, editable from /tune) ----------------------
create table scoring_config (
  id integer primary key default 1 check (id = 1),
  config jsonb not null,
  updated_at timestamptz not null default now()
);
insert into scoring_config (id, config) values (1, '{}'::jsonb)
  on conflict (id) do nothing;

-- 8. Updated-at triggers ---------------------------------------------------
create or replace function set_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end;
$$;

create trigger jobs_updated_at before update on jobs
  for each row execute function set_updated_at();
create trigger applications_updated_at before update on applications
  for each row execute function set_updated_at();

-- 9. RLS -------------------------------------------------------------------
alter table jobs enable row level security;
alter table resumes enable row level security;
alter table job_scores enable row level security;
alter table applications enable row level security;
alter table sources_health enable row level security;
alter table spend_tracking enable row level security;
alter table scoring_config enable row level security;

-- public reads for the public stuff
create policy jobs_read_all on jobs for select using (true);
create policy sources_read_all on sources_health for select using (true);
create policy scoring_config_read_all on scoring_config for select using (true);

-- per-user reads on private tables
create policy resumes_owner_read on resumes for select
  using (auth.uid() = user_id);
create policy resumes_owner_write on resumes for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy applications_owner_read on applications for select
  using (auth.uid() = user_id);
create policy applications_owner_write on applications for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy job_scores_owner_read on job_scores for select
  using (
    exists (
      select 1 from resumes r
      where r.id = job_scores.resume_id and r.user_id = auth.uid()
    )
  );

create policy spend_owner_read on spend_tracking for select
  using (auth.uid() is not null);  -- single user, just check authed

-- 10. Allowed-email guard (single-user enforcement) ------------------------
-- Set via Supabase Dashboard: Authentication → Providers → Email →
-- "Confirm email" ON, and use a trigger:
create or replace function block_unauthorized_signups()
returns trigger language plpgsql as $$
begin
  if new.email != 'eugeniogdelatorre@gmail.com' then
    raise exception 'Signup not allowed for %', new.email;
  end if;
  return new;
end;
$$;

create trigger restrict_signup
  before insert on auth.users
  for each row execute function block_unauthorized_signups();
```

---

## 3. Project File Structure

```
job-search-agent-v3/
├── README.md
├── LICENSE                     # MIT
├── .gitignore
├── .env.example                # for local dev only
├── .github/
│   └── workflows/
│       ├── scrape.yml
│       ├── classify.yml
│       ├── cv_score.yml
│       └── weekly_summary.yml
├── scraper/
│   ├── requirements.txt        # requests, beautifulsoup4, pdfplumber, supabase, anthropic
│   ├── pyproject.toml          # ruff + mypy config
│   ├── sources.json            # ported from v2 career_sources.json
│   ├── sources.py              # source loader, group selection
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── base.py             # Parser protocol
│   │   ├── greenhouse.py
│   │   ├── lever.py
│   │   ├── ashby.py
│   │   ├── workday.py
│   │   ├── cryptojobslist.py
│   │   ├── web3career.py
│   │   ├── weworkremotely.py   # ports the unmasher from v2
│   │   └── generic.py          # fallback HTML parser
│   ├── dedup.py
│   ├── score.py                # 6-dim rule-based scorer, reads scoring_config
│   ├── classify.py             # Haiku Batch API for function/seniority/vertical
│   ├── cv_score.py             # Haiku Batch API for CV match
│   ├── weekly_summary.py       # builds + sends weekly email via Resend
│   ├── budget.py               # spend cap enforcement
│   ├── supabase_client.py      # service-role client wrapper
│   ├── retention.py            # 60-day delete + 7-day inactive marker
│   └── scrape.py               # orchestrator entry point
├── web/
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── postcss.config.js
│   ├── next.config.mjs
│   ├── .env.local.example
│   ├── components.json         # shadcn config
│   ├── src/
│   │   ├── middleware.ts       # auth gate
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── globals.css
│   │   │   ├── page.tsx                # /
│   │   │   ├── login/page.tsx
│   │   │   ├── auth/callback/route.ts
│   │   │   ├── week/page.tsx
│   │   │   ├── archive/page.tsx
│   │   │   ├── apply/page.tsx
│   │   │   ├── resume/page.tsx
│   │   │   ├── tune/page.tsx
│   │   │   ├── settings/page.tsx
│   │   │   └── api/
│   │   │       ├── cv/
│   │   │       │   ├── upload/route.ts
│   │   │       │   └── activate/route.ts
│   │   │       ├── applications/route.ts
│   │   │       ├── export/route.ts
│   │   │       ├── spend/route.ts
│   │   │       └── tune/route.ts
│   │   ├── components/
│   │   │   ├── JobCard.tsx
│   │   │   ├── JobList.tsx
│   │   │   ├── FilterBar.tsx
│   │   │   ├── MatchBadge.tsx
│   │   │   ├── KanbanBoard.tsx
│   │   │   ├── KanbanCard.tsx
│   │   │   ├── ResumeUploader.tsx
│   │   │   ├── SpendChart.tsx
│   │   │   ├── SourceHealthTable.tsx
│   │   │   ├── ScoringConfigEditor.tsx
│   │   │   └── ui/                     # shadcn components live here
│   │   ├── lib/
│   │   │   ├── supabase/server.ts
│   │   │   ├── supabase/client.ts
│   │   │   ├── pdf-parse.ts            # uses pdf-parse npm package
│   │   │   ├── filters.ts              # filter state -> SQL builder
│   │   │   └── format.ts               # money, date, % helpers
│   │   └── types/
│   │       └── db.ts                   # supabase gen types --typescript
└── docs/
    ├── ARCHITECTURE.md
    ├── PROMPTS.md                      # the locked AI prompts
    ├── RUNBOOK.md                      # what to do when things break
    └── COST_MATH.md
```

---

## 4. AI Prompts (locked: do not improvise)

### 4.1 Classification

System message:
```
You extract structured fields from Web3 job postings. Return JSON only, no prose, no code fences.
```

User message template:
```
Title: {title}
Company: {company}
Location: {location}
Description: {description_first_2000_chars}

Return this exact shape:
{
  "function_category": "Community" | "Design" | "Engineering" | "Marketing" | "Operations" | "Sales" | "BizDev" | "Product" | "Other",
  "function_confidence": 0.0,
  "seniority": "Junior" | "Mid" | "Senior" | "Lead" | "Head" | "Executive" | "Unspecified",
  "vertical": "DeFi" | "L1" | "L2" | "CEX" | "DEX" | "Gaming" | "Infrastructure" | "NFT" | "RWA" | "Oracles" | "AI-Crypto" | "Other",
  "salary_min_usd": null,
  "salary_max_usd": null,
  "remote_status": "Remote" | "Hybrid" | "Onsite" | "Unspecified"
}

Rules:
- Use Unspecified, Other, or null when genuinely uncertain. Do not guess.
- Salary fields only filled when explicitly stated in the description (numbers + USD or unambiguous currency).
- function_confidence is your confidence in function_category from 0.0 to 1.0.
```

Token budget: ~400 in, ~80 out. Submit via Batch API.

### 4.2 CV Scoring (with prompt caching)

System message (CACHED with `cache_control: {type: "ephemeral"}`):
```
You score Web3 job postings against a candidate's resume. Be honest. Inflated scores waste the candidate's time. Return JSON only, no prose, no code fences.

CANDIDATE RESUME:
---
{full_parsed_cv_text}
---
```

User message template (per job, NOT cached):
```
Score this job against the candidate's resume above.

Job:
- Title: {title}
- Company: {company}
- Vertical: {vertical}
- Function: {function_category}
- Seniority: {seniority}
- Description: {description_first_3000_chars}

Return this exact shape:
{
  "match_score": 0,
  "strengths": ["", "", ""],
  "gaps": ["", "", ""],
  "verdict_one_liner": ""
}

Scoring rubric:
- 80-100: Strong match. Apply now. Resume already shows the required experience.
- 60-79:  Decent match. Worth tailoring CV for. Some required experience missing or weak.
- 40-59:  Weak match. Significant gaps. Only apply if you are willing to upskill or pivot.
- 0-39:   Not a match. Do not apply.

strengths: up to 3 items, each <= 80 chars, citing specific resume bullets that match the JD.
gaps: up to 3 items, each <= 80 chars, naming what's missing or weak.
verdict_one_liner: single sentence under 120 chars.
```

Token budget: ~3500 in cached + ~600 in fresh + ~250 out. Submit via Batch API. Prompt caching reduces cached read cost by ~90%.

### 4.3 Weekly summary email

Plain Python templating, no AI. Just SQL → HTML.

---

## 5. GitHub Actions Workflows (cron + skeletons)

### scrape.yml
- Trigger: cron `0 */4 * * *` (every 4h) + workflow_dispatch
- Matrix: split sources into 2 groups, parallel jobs
- Steps: checkout, setup-python, pip install, run `python scraper/scrape.py --group $GROUP`
- Secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
- Concurrency: cancel in-progress runs of the same group

### classify.yml
- Trigger: cron `0 6 * * *` + workflow_dispatch
- Steps: checkout, setup-python, pip install, run `python scraper/classify.py`
- Secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `ANTHROPIC_API_KEY`
- Timeout: 30 min (Batch API can take a while)

### cv_score.yml
- Trigger: cron `0 7 * * *` (after classify) + workflow_dispatch
- Steps: as above, runs `python scraper/cv_score.py`
- Same secrets

### weekly_summary.yml
- Trigger: cron `0 22 * * 0` (Sun 22:00 UTC = Sun 7pm ART) + workflow_dispatch
- Steps: runs `python scraper/weekly_summary.py`
- Extra secret: `RESEND_API_KEY`
- Recipient is hardcoded to eugeniogdelatorre@gmail.com (single user)

---

## 6. Build Order for Claude Code

Execute phase by phase. Each phase ends with a checkpoint Eugenio can verify before moving on. Do not skip ahead.

### Phase 0: Repo + infra setup
1. Create new GitHub repo `eugeniogdelatorre-del/job-search-agent-v3`. **Public.**
2. Add LICENSE (MIT), .gitignore (Python + Node + .env), README skeleton
3. Create new Supabase project, name it `job-agent-v3`, region São Paulo
4. Run the schema SQL from §2 in the Supabase SQL editor
5. Verify tables exist via `select * from information_schema.tables where table_schema = 'public'`
6. Configure Supabase Auth: enable Email provider, magic link only, disable signups via dashboard (the trigger in §2 is belt-and-braces)
7. Get Anthropic API key (Eugenio provides), Resend API key (Eugenio creates a free account, provides)

**Checkpoint 0:** Eugenio confirms repo exists, schema deployed, all 3 keys ready in a password manager.

### Phase 1: Scraper bones
1. Set up `scraper/` directory with requirements.txt: `requests`, `beautifulsoup4`, `lxml`, `pdfplumber`, `supabase`, `anthropic`
2. Eugenio supplies `career_sources.json` from v2 repo. Drop into `scraper/sources.json` as-is for now.
3. Implement `sources.py`: load json, group selection
4. Implement `parsers/base.py`: `Parser` protocol with `parse(html, source_meta) -> list[dict]`
5. Implement `parsers/greenhouse.py` and `parsers/lever.py` first (most reliable APIs)
6. Implement `dedup.py`: normalize(title + company), tier-aware tie-break
7. Implement `score.py`: 6-dim rule-based (port logic from v2 `scrape.py`, but read weights from `scoring_config` table)
8. Implement `supabase_client.py`: service-role client wrapper with upsert helper
9. Implement `retention.py`: mark inactive after 7 days, hard delete after 60 days
10. Implement `scrape.py` orchestrator: load sources for group → fetch each → parse → dedup within group → score → upsert → log to sources_health

**Checkpoint 1:** Run `python scraper/scrape.py --group 1` locally. Verify rows land in Supabase. Eugenio inspects 10 random rows for sanity.

### Phase 2: Remaining parsers + workflow
1. Implement remaining parsers: `ashby.py`, `workday.py`, `cryptojobslist.py`, `web3career.py`, `weworkremotely.py` (port unmasher from v2 migration script), `generic.py`
2. Add junk filters: drop X/Twitter feeds entirely, drop sidebar-ad rows by marker list (port from v2)
3. Cross-source dedup pass after group results merge
4. Write `.github/workflows/scrape.yml` (every 4h, matrix on groups)
5. Add GitHub Secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
6. Trigger workflow_dispatch run, verify jobs land

**Checkpoint 2:** First scheduled scrape lands cleanly. `select count(*) from jobs` shows >100. Eugenio inspects 20 random rows: zero junk, zero mash-ups.

### Phase 3: Classification
1. Implement `budget.py`: function `assert_under_budget()` reads `spend_tracking`, raises if MTD > $8
2. Implement `classify.py`: query unclassified jobs → submit Batch API → poll → write back → log spend
3. Write `.github/workflows/classify.yml`
4. Add GitHub Secret: `ANTHROPIC_API_KEY`
5. Trigger run, verify function_category populates

**Checkpoint 3:** All current jobs have function_category. Spend logged to spend_tracking. Cost less than $0.10.

### Phase 4: Web app skeleton + auth
1. Scaffold Next.js 14 app under `web/`: `npx create-next-app@latest --ts --tailwind --app --src-dir --import-alias "@/*"`
2. Install deps: `@supabase/ssr`, `@supabase/supabase-js`, `pdf-parse`, `lucide-react`, shadcn-ui CLI
3. Initialize shadcn-ui, add components: button, card, badge, input, dialog, dropdown-menu, table, tabs, sonner (toast)
4. Implement `lib/supabase/server.ts` and `lib/supabase/client.ts` using `@supabase/ssr` server/client patterns
5. Implement `middleware.ts`: redirect to /login if no session, except for /login and /auth/callback
6. Build `/login` page: email input → `signInWithOtp` → "check your email"
7. Build `/auth/callback/route.ts`: handle magic link
8. Build minimal `/` page: just "Hello, {email}" + sign out button
9. Deploy to Vercel. Add env vars: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`
10. Eugenio logs in end-to-end via magic link

**Checkpoint 4:** Eugenio can log in on the deployed Vercel URL. Unauthorized email is blocked by the SQL trigger.

### Phase 5: Job views (Today / Week / Archive)
1. Build `components/FilterBar.tsx`: function, vertical, seniority, remote/hybrid/onsite, salary floor (with D8 behavior: include nulls), score threshold, AI match threshold, posted-within, keyword search
2. Build `components/MatchBadge.tsx`: visual % with color (red <40, yellow 40-59, blue 60-79, green 80+)
3. Build `components/JobCard.tsx`: title, company, location, salary range, badges (function, vertical, seniority, source tier), match% if scored, strengths/gaps preview, "Save to tracker" button, "Apply" link
4. Build `components/JobList.tsx`: pass filter state, query Supabase, render cards
5. Build `/` (Today): jobs from last 24h, default sort = match% desc, FilterBar at top
6. Build `/week`: top 100 by match% from last 7 days
7. Build `/archive`: full filters, paginated table view (denser than cards), 50/page

**Checkpoint 5:** Eugenio opens / and sees today's jobs. Filters work. Match% sort works (will show "Not yet scored" for jobs that haven't been CV-scored yet: that's expected, comes online in Phase 6).

### Phase 6: CV upload + AI scoring
1. Build `/resume` page: ResumeUploader component (PDF drag-drop, max 5MB), version list table, "Activate" button
2. Build `/api/cv/upload` route: receive PDF → parse text via `pdf-parse` → SHA-256 hash → check duplicates → insert resume row → if first, set is_active=true
3. Build `/api/cv/activate` route: set is_active on chosen, false on others (RLS enforces ownership)
4. Implement `scraper/cv_score.py`: query active resume, find jobs with score_total >= 60 lacking job_scores row, submit Batch API with prompt caching, write back
5. Write `.github/workflows/cv_score.yml`
6. Trigger first run

**Checkpoint 6:** Eugenio uploads a CV, activates it, runs cv_score workflow manually, refreshes / view, sees match%s populated with strengths/gaps. Inspects 5 jobs to validate scoring quality.

### Phase 7: Apply tracker
1. Build `/api/applications` route: POST creates with snapshot fields, PUT updates status/notes
2. Build `components/KanbanCard.tsx`, `components/KanbanBoard.tsx` (5 columns: Saved, Applied, Interview, Offer, Rejected)
3. Build `/apply` page: query applications for current user, group by status, drag-drop to change status (use `@dnd-kit/core`)
4. Add "Save to tracker" button on JobCard → POST /api/applications with snapshot
5. Add "applied_at" auto-fill when status moves to Applied

**Checkpoint 7:** Eugenio saves 3 jobs, drags one to Applied, adds notes. Refreshes, state persists.

### Phase 8: Tune / Settings / Export / Weekly summary
1. Build `/tune`: ScoringConfigEditor component, edits jsonb in scoring_config table. POST to /api/tune
2. Build `/settings`: SpendChart (daily spend last 30d), SourceHealthTable (last run per source, success/fail), account info, sign out
3. Build `/api/export`: takes filter, returns CSV or JSON or Notion-compatible CSV
4. Add "Export N jobs" button on each list view
5. Implement `scraper/weekly_summary.py`: query top 10 by match_score from past 7d → render HTML email → send via Resend
6. Write `.github/workflows/weekly_summary.yml`
7. Trigger manually to verify email arrives at eugeniogdelatorre@gmail.com

**Checkpoint 8:** Weekly summary lands in inbox. Spend dashboard shows MTD cost. Source health shows green/red per scraper. Export downloads cleanly.

### Phase 9: Polish + docs
1. Spend cap email alert: when budget.py trips, send Resend email "Job agent paused, MTD spend = $X"
2. Loading states + empty states on every page
3. Write `docs/RUNBOOK.md`: how to add a new source, how to debug a dead scraper, how to rotate keys
4. Write `docs/COST_MATH.md` with actual MTD numbers from spend_tracking
5. README with screenshots
6. Final pass: `ruff check`, `mypy`, `tsc --noEmit`, `eslint`, all clean
7. Update `docs/ARCHITECTURE.md` with anything that drifted during build

**Checkpoint 9:** Ship. Eugenio uses it as his daily driver. Bugs filed as GitHub issues.

---

## 7. Env Vars & Secrets Checklist

### GitHub Secrets (Settings → Secrets and variables → Actions)
| Name | Used by | Source |
|---|---|---|
| `SUPABASE_URL` | scraper | Supabase project settings |
| `SUPABASE_SERVICE_KEY` | scraper | Supabase project settings → API → service_role |
| `ANTHROPIC_API_KEY` | classify, cv_score | console.anthropic.com |
| `RESEND_API_KEY` | weekly_summary | resend.com dashboard |

### Vercel Environment Variables (Project → Settings → Environment Variables)
| Name | Scope | Source |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Production + Preview | Supabase project settings |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Production + Preview | Supabase project settings → API → anon (safe in browser) |
| `SUPABASE_SERVICE_KEY` | Production only | Same as GitHub. Used by /api routes that need to bypass RLS. |
| `RESEND_API_KEY` | Production only | For spend-cap email alerts |

### Local dev (.env.local: not committed)
Same as Vercel, but only `NEXT_PUBLIC_*` and a dev `SUPABASE_SERVICE_KEY` if running API routes locally.

**Never commit any of the above. .gitignore must include `.env*` (except `.env.example` and `.env.local.example`).**

---

## 8. Spend Math (revised for ~100 active jobs)

| Operation | Volume / month | Tokens per call | Cost per call | Monthly |
|---|---|---|---|---|
| Classification | ~300 new jobs/mo (after dedup) | ~400 in + ~80 out | $0.0002 (Batch) | **~$0.06** |
| CV scoring | ~180 jobs above warm threshold | ~3500 cached + ~600 fresh + ~250 out | ~$0.0009 (Batch + cache) | **~$0.16** |
| Weekly summary | 4 emails | n/a, no AI | $0 (Resend free tier) | **$0** |
| **Total AI** | | | | **~$0.22/mo** |

That's against an $8 hard cap and $10 ceiling. Massive headroom. The cap exists to catch a runaway loop (classifier in retry hell, infinite Batch resubmits, etc.), not because we expect to hit it.

If the active job count grows 5x (to ~500), AI spend scales linearly to ~$1.10/mo. Still trivial.

---

## 9. Items to Confirm During Build

These came up while writing the plan. None block kickoff, but Claude Code should ask before deciding:

1. **Apply URL hygiene.** Some sources give tracking-laden URLs (`?utm_source=...`). Strip params on display, or keep full?
2. **CV deletion UX.** When you upload a new CV, do old versions stay forever (last 5 default)? Or auto-delete after N days? Currently spec'd: keep last 5.
3. **Source list editing.** Should `/settings` let you toggle individual sources on/off? Or is `sources.json` in the repo the only way? Current spec: repo-only, edit and PR.
4. **Notification on first 80+ match.** Want a Resend email the moment a freshly-scored job lands above 80? Defaults: no, weekly only. Easy to add later.

---

## 10. What Eugenio Hands to Claude Code

Open the new project chat with Claude Code and paste the following:

> Project: job-search-agent-v3, fresh greenfield rebuild. The full architecture and build plan is in JOB_SEARCH_AGENT_V3_PLAN.md (attached). Work through phases 0-9 in order. Stop at every checkpoint and wait for me to verify before moving on. Do not improvise on the schema, the AI prompts, or the file structure. If you hit a question that's not answered in the plan, ask before assuming.

Plus attach:
- This file (`JOB_SEARCH_AGENT_V3_PLAN.md`)
- `career_sources.json` from the v2 repo (Eugenio pulls this from the old repo and uploads)

That's it. No other v2 files needed.
