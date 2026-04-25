'use client'

// FilterBar — dark redesign. Pushes changes into URL search params.
// All inputs share dark fill + cyan focus. Uses inline styles for design-specific
// colors; Tailwind for layout/spacing.

import { useRouter, usePathname, useSearchParams } from 'next/navigation'
import { useTransition } from 'react'
import {
  FUNCTION_CATEGORIES,
  REMOTE_STATUSES,
  SENIORITIES,
  VERTICALS,
} from '@/types/db'
import { FILTER_KEYS } from '@/lib/filters'

const INPUT_BASE: React.CSSProperties = {
  background:   'rgba(255,255,255,0.03)',
  border:       '1px solid #1E2330',
  borderRadius: '6px',
  color:        '#E8ECF0',
  fontFamily:   'var(--font-mono)',
  fontSize:     '11px',
  padding:      '6px 10px',
  height:       '34px',
  outline:      'none',
  transition:   'border-color 0.15s, box-shadow 0.15s',
}

const SELECT_BASE: React.CSSProperties = {
  ...INPUT_BASE,
  paddingRight:       '28px',
  backgroundRepeat:   'no-repeat',
  backgroundPosition: 'right 8px center',
  cursor:             'pointer',
} as React.CSSProperties

function onFocus(e: React.FocusEvent<HTMLElement>) {
  e.target.style.borderColor = '#00D4FF'
  e.target.style.boxShadow   = '0 0 0 2px rgba(0,212,255,0.15)'
}
function onBlur(e: React.FocusEvent<HTMLElement>) {
  e.target.style.borderColor = '#1E2330'
  e.target.style.boxShadow   = 'none'
}

type Props = { hidePostedWithin?: boolean }

export function FilterBar({ hidePostedWithin }: Props) {
  const router       = useRouter()
  const pathname     = usePathname()
  const searchParams = useSearchParams()
  const [isPending, startTransition] = useTransition()

  function update(key: string, value: string) {
    const next = new URLSearchParams(searchParams.toString())
    if (value) next.set(key, value)
    else next.delete(key)
    startTransition(() => {
      router.replace(`${pathname}?${next.toString()}`, { scroll: false })
    })
  }

  function reset() {
    startTransition(() => router.replace(pathname, { scroll: false }))
  }

  const val        = (k: string) => searchParams.get(k) ?? ''
  const hasFilters = FILTER_KEYS.some((k) => searchParams.get(k))

  return (
    <div
      className="flex flex-wrap items-center gap-2 rounded-[10px] p-3.5"
      style={{ background: '#0F1117', border: '1px solid #1E2330' }}
    >
      {/* Search input */}
      <div className="relative flex items-center" style={{ flexGrow: 1, minWidth: '180px' }}>
        <svg
          className="absolute left-2.5 pointer-events-none"
          width="12" height="12" viewBox="0 0 24 24"
          fill="none" stroke="#6B7A99" strokeWidth="2"
          strokeLinecap="round" strokeLinejoin="round"
        >
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <input
          type="search"
          placeholder="Search title / company"
          className="w-full pl-8 focus:outline-none focus:ring-0"
          style={INPUT_BASE}
          defaultValue={val('q')}
          onFocus={onFocus}
          onBlur={(e) => { onBlur(e); update('q', e.target.value) }}
          onKeyDown={(e) => { if (e.key === 'Enter') update('q', (e.target as HTMLInputElement).value) }}
        />
      </div>

      {/* Divider */}
      <div style={{ width: 1, height: 24, background: '#1E2330', flexShrink: 0 }} />

      {/* Selects */}
      <select style={SELECT_BASE} value={val('function')}  onChange={(e) => update('function',  e.target.value)} onFocus={onFocus} onBlur={onBlur}>
        <option value="">Any function</option>
        {FUNCTION_CATEGORIES.map((v) => <option key={v} value={v}>{v}</option>)}
      </select>
      <select style={SELECT_BASE} value={val('vertical')}  onChange={(e) => update('vertical',  e.target.value)} onFocus={onFocus} onBlur={onBlur}>
        <option value="">Any vertical</option>
        {VERTICALS.map((v) => <option key={v} value={v}>{v}</option>)}
      </select>
      <select style={SELECT_BASE} value={val('seniority')} onChange={(e) => update('seniority', e.target.value)} onFocus={onFocus} onBlur={onBlur}>
        <option value="">Any seniority</option>
        {SENIORITIES.map((v) => <option key={v} value={v}>{v}</option>)}
      </select>
      <select style={SELECT_BASE} value={val('remote')}    onChange={(e) => update('remote',    e.target.value)} onFocus={onFocus} onBlur={onBlur}>
        <option value="">Any location</option>
        {REMOTE_STATUSES.map((v) => <option key={v} value={v}>{v}</option>)}
      </select>

      {/* Divider */}
      <div style={{ width: 1, height: 24, background: '#1E2330', flexShrink: 0 }} />

      {/* Numeric inputs */}
      <input type="number" placeholder="min $"    style={{ ...INPUT_BASE, width: 80 }} min={0} defaultValue={val('salaryFloor')} onFocus={onFocus} onBlur={(e) => { onBlur(e); update('salaryFloor', e.target.value) }} />
      <input type="number" placeholder="rule ≥"   style={{ ...INPUT_BASE, width: 64 }} min={0} defaultValue={val('scoreMin')}    onFocus={onFocus} onBlur={(e) => { onBlur(e); update('scoreMin',    e.target.value) }} />
      <input type="number" placeholder="match ≥"  style={{ ...INPUT_BASE, width: 64 }} min={0} defaultValue={val('matchMin')}    onFocus={onFocus} onBlur={(e) => { onBlur(e); update('matchMin',    e.target.value) }} />

      {!hidePostedWithin && (
        <select style={SELECT_BASE} value={val('postedWithin')} onChange={(e) => update('postedWithin', e.target.value)} onFocus={onFocus} onBlur={onBlur}>
          <option value="">Any date</option>
          <option value="1d">Last 24h</option>
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
        </select>
      )}

      {hasFilters && (
        <button
          onClick={reset}
          disabled={isPending}
          className="font-mono text-[10px] font-medium rounded px-2.5 py-1 transition-colors"
          style={{ background: 'transparent', border: '1px solid #252D40', color: '#6B7A99' }}
          onMouseEnter={(e) => { e.currentTarget.style.color = '#E8ECF0'; e.currentTarget.style.borderColor = '#6B7A99' }}
          onMouseLeave={(e) => { e.currentTarget.style.color = '#6B7A99'; e.currentTarget.style.borderColor = '#252D40' }}
        >
          clear ✕
        </button>
      )}
    </div>
  )
}
