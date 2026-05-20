// Single source of truth for the monthly spend cap displayed in the UI.
//
// 2026-05-14 (Audit H8): previously hardcoded as `8` in
// web/src/app/api/spend/route.ts and `web/src/app/settings/page.tsx`,
// and again as `BUDGET_CAP_USD = 8.00` in scraper/budget.py. The
// $8 → $20 → $30 bumps exposed that the three values are easy to drift
// apart. Centralising the TS side here so future changes touch one file.
//
// The canonical value lives in scraper/budget.py. Treat this constant
// as a mirror; if you change one, change the other in the same commit.
// scraper/tests/test_budget_caps_match_ui.py fails CI on any drift
// (Audit C1, 2026-05-19 — the $30/$20/$12/$3 drift this audit caught
// was an unguarded cap change two weeks back).
//
// We picked a TS module over an env var so the value is type-safe and
// shipped with the bundle (no risk of a missing env var falling back
// to a tiny default at runtime).

export const MONTHLY_CAP_USD = 30

// Per-stage caps. Mirror of STAGE_BUDGETS in scraper/budget.py. Not
// currently shown anywhere in the UI but reserved for an upcoming
// per-stage progress widget on /settings.
export const STAGE_CAPS_USD = {
  classify:   5,
  geo_filter: 5,
  cv_score:  20,
} as const
