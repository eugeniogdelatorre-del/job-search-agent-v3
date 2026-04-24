# COST_MATH

Projected and actual spend. Cap: **$8/mo hard**, ceiling $10/mo.

## Projection (from plan §8, at ~100 active jobs)

| Operation | Volume | Tokens/call | Cost/call | Monthly |
|---|---|---|---|---|
| Classification | ~300 new jobs/mo | 400 in + 80 out | $0.0002 | **~$0.06** |
| CV scoring | ~180 warm jobs/mo | 3500 cached + 600 fresh + 250 out | ~$0.0009 | **~$0.16** |
| Weekly summary | 4 / mo | n/a | $0 | **$0** |
| **Total AI** | | | | **~$0.22/mo** |

Linear scaling: at 5× volume (~500 active jobs), AI spend is ~$1.10/mo.

## Why the cap is $8

Cap exists to catch a runaway loop (classifier retry hell, infinite
Batch resubmits), not expected usage. $8 sits well under the $10
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

- **Raise the warm threshold** in `scraper/cv_score.py` (currently 60
  rule score). Going to 70 cuts CV-scored volume roughly in half.
- **Shrink description truncation** in prompts (§4.1 uses 2000, §4.2
  uses 3000). Trim to reduce input tokens at a quality cost.
- **Drop junk sources**. Aggregator tier 1 sources often produce
  low-match jobs that waste classification budget. Weed via the
  source health table.
