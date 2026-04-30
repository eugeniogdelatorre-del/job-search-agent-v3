// Filter state is carried in URL search params so sharing + back-button
// work for free and server components can read filters on render.
//
// D8: when salary_floor is set, jobs with null salary_max are STILL shown
// (implemented as OR filter below).

import type {
  FunctionCategory,
  RemoteStatus,
  Seniority,
  Vertical,
} from '@/types/db'

export type Filters = {
  function?: FunctionCategory
  vertical?: Vertical
  seniority?: Seniority
  remote?: RemoteStatus
  salaryFloor?: number
  matchMin?: number
  postedWithin?: '1d' | '7d' | '30d'
  q?: string
}

export const FILTER_KEYS = [
  'function',
  'vertical',
  'seniority',
  'remote',
  'salaryFloor',
  'matchMin',
  'postedWithin',
  'q',
] as const

export function parseFilters(sp: Record<string, string | string[] | undefined>): Filters {
  const get = (k: string) => {
    const v = sp[k]
    return typeof v === 'string' && v.length > 0 ? v : undefined
  }
  const num = (k: string) => {
    const v = get(k)
    if (v === undefined) return undefined
    const n = Number(v)
    return Number.isFinite(n) ? n : undefined
  }
  return {
    function: get('function') as FunctionCategory | undefined,
    vertical: get('vertical') as Vertical | undefined,
    seniority: get('seniority') as Seniority | undefined,
    remote: get('remote') as RemoteStatus | undefined,
    salaryFloor: num('salaryFloor'),
    matchMin: num('matchMin'),
    postedWithin: get('postedWithin') as Filters['postedWithin'],
    q: get('q'),
  }
}

export function filtersToSearchParams(f: Filters): URLSearchParams {
  const sp = new URLSearchParams()
  for (const k of FILTER_KEYS) {
    const v = f[k]
    if (v !== undefined && v !== '' && v !== null) {
      sp.set(k, String(v))
    }
  }
  return sp
}

export function postedWithinCutoff(v: Filters['postedWithin']): Date | null {
  if (!v) return null
  const now = Date.now()
  const ms =
    v === '1d' ? 86400e3 : v === '7d' ? 7 * 86400e3 : v === '30d' ? 30 * 86400e3 : 0
  return ms ? new Date(now - ms) : null
}
