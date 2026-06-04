import { describe, it, expect } from 'vitest'
import { MONTHLY_CAP_USD, STAGE_CAPS_USD } from './budget-config'

// NOTE on the sum invariant:
// Stage caps are *per-op early-warning trips*, not a budget allocation.
// The global MONTHLY_CAP_USD is the hard ceiling regardless of the sum
// of stage caps (see scraper/budget.py line 53). Therefore we do NOT
// assert sum(STAGE_CAPS_USD) === MONTHLY_CAP_USD. Instead we guard
// against per-stage and global-cap drift between TS and Python.

describe('budget-config', () => {
  it('MONTHLY_CAP_USD is a positive number', () => {
    expect(typeof MONTHLY_CAP_USD).toBe('number')
    expect(MONTHLY_CAP_USD).toBeGreaterThan(0)
  })

  it('MONTHLY_CAP_USD matches the canonical Python BUDGET_CAP_USD ($30)', () => {
    // Mirror of BUDGET_CAP_USD in scraper/budget.py.
    // If you bump one, bump the other in the same commit.
    expect(MONTHLY_CAP_USD).toBe(30)
  })

  it('all required stages are present in STAGE_CAPS_USD', () => {
    const requiredStages = ['classify', 'geo_filter', 'cv_score', 'cv_extract'] as const
    for (const stage of requiredStages) {
      expect(STAGE_CAPS_USD).toHaveProperty(stage)
    }
  })

  it('each stage cap is a positive number', () => {
    for (const [stage, cap] of Object.entries(STAGE_CAPS_USD)) {
      expect(typeof cap, `stage "${stage}" cap should be a number`).toBe('number')
      expect(cap, `stage "${stage}" cap should be positive`).toBeGreaterThan(0)
    }
  })

  it('per-stage caps match canonical Python STAGE_BUDGETS (drift guard)', () => {
    // Mirror of STAGE_BUDGETS in scraper/budget.py.
    // If you change a cap in Python, update it here in the same commit.
    // scraper/tests/test_budget_caps_match_ui.py also guards this from the Python side.
    expect(STAGE_CAPS_USD.classify).toBe(5)
    expect(STAGE_CAPS_USD.geo_filter).toBe(5)
    expect(STAGE_CAPS_USD.cv_score).toBe(20)
    expect(STAGE_CAPS_USD.cv_extract).toBe(1)
  })
})
