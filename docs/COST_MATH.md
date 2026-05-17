# COST_MATH

Projected and actual spend. Caps (raised 2026-05-16): **$30/mo hard global**, per-stage **classify $5 / geo_filter $5 / cv_score $20**.

## Projection (from plan §8, at ~100 active jobs)

| Operation | Volume | Tokens/call | Cost/call | Monthly |
|---|---|---|---|---|
| Classification | ~300 new jobs/mo | 400 in + 80 out | $0.0002 | **~$0.06** |
| CV scoring | ~180 warm jobs/mo | 3500 cached + 600 fresh + 250 out | ~$0.0009 | **~$0.16** |
| Weekly summary | 4 / mo | n/a | $0 | **$0** |
| **Total AI** | | | | **~$0.22/mo** |

Linear scaling: at 5× volume (~500 active jobs), AI spend is ~$1.10/mo.

## Why the cap is $30 (and cv_score is gated at $20)

Caps exist to catch runaway loops (classifier retry hell, infinite
Batch resubmits, cache misconfig, dedup-key collisions) and to absorb
one-off remediation runs without manual intervention. The split keeps
cv_score from monopolizing the budget while still letting the other
stages run if cv_score trips. $30 was reached iteratively as real
incidents exposed too-tight ceilings: $8 → $20 (2026-05-14, dedup
duplicate-scoring) → $30 (2026-05-16, cache TTL beta-header gap;
classify and geo_filter also raised to $5 each for surprise-spike
headroom). The $30 sits well under any harder ceiling so retries
ceiling so the Resend alert email and any retries between trip and
notification still fit in budget.

## Pricing reference (as of 2026-04)

- **Haiku 4.5 base:** $1 / $5 per MTok (in / out)
- **Batch API discount:** 50% off base
- **Prompt caching:**
  - cache write: 1.25× base input
  - cache read: 0.1× base input
- **Resend:** free tier covers 3000 emails/month

## Actual MTD

The SpendChart on `/settings` surfaces live numbers. Raw source of
truth:

```sql
select
  date_trunc('day', run_at) as day,
  operation,
  sum(cost_usd) as usd,
  sum(input_tokens) as in_tok,
  sum(cached_input_tokens) as cache_in_tok,
  sum(output_tokens) as out_tok
from spend_tracking
where run_at >= date_trunc('month', now())
group by 1, 2
order by 1 desc, 2;
```

Update this file quarterly with real numbers as they stabilize.

## Knobs when/if costs climb

- **Raise the warm threshold** in `scraper/cv_score.py`
  (`WARM_THRESHOLD`, currently 60). Going to 70 cuts CV-scored volume
  roughly in half. Keep `classify.CLASSIFY_MIN_SCORE` in sync —
  `classify.py` only classifies jobs at or above the warm threshold,
  so jobs below it never reach cv_score and never need classification.
- **Shorten the cv_score age window.** `cv_score.MAX_JOB_AGE_DAYS`
  (default 15) skips jobs whose `first_seen_at` is older. Drop it
  further to cut backlog spend; raise it if you want to score older
  postings that are still active.
- **Shrink description truncation** in prompts (§4.1 uses 2000, §4.2
  uses 3000). Trim to reduce input tokens at a quality cost.
- **Drop junk sources**. Aggregator tier 1 sources often produce
  low-match jobs that waste classification budget. Weed via the
  source health table.
