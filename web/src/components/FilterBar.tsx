'use client'

// FilterBar — dark redesign. Pushes changes into URL search params.
// Uses CustomSelect for fully-dark dropdown popups (native <select> popup
// can't be CSS-forced dark cross-platform).

import { useRouter, usePathname, useSearchParams } from 'next/navigation'
import { useTransition } from 'react'
import {
  FUNCTION_CATEGORIES,
  REMOTE_STATUSES,
  SENIORITIES,
  VERTICALS,
} from '@/types/db'
import { FILTER_KEYS } from '@/lib/filters'
import { CustomSelect } from '@/components/CustomSelect'

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
  colorScheme:  'dark',
}

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
  // Audit M16: <input defaultValue=…> only reads on mount. Back/Forward
  // changes the URL but doesn't remount, so the input keeps its old
  // text and the visible filter disagrees with the URL state. Pinning
  // a `key` derived from the URL forces a remount whenever the search
  // params change, so the defaultValue is re-read.
  const urlKey = searchParams.toString()

  return (
    <div
      className="flex flex-wrap items-center gap-2 rounded-[10px] p-3.5"
      style={{ background: '#0F1117', border: '1px solid #1E2330' }}
    >
      {/* Search input */}
      <input
        key={`q-${urlKey}`}
        type="search"
        placeholder="Search title / company"
        className="focus:outline-none focus:ring-0"
        style={{ ...INPUT_BASE, flexGrow: 1, minWidth: '180px' }}
        defaultValue={val('q')}
        onFocus={onFocus}
        onBlur={(e) => { onBlur(e); update('q', e.target.value) }}
        onKeyDown={(e) => { if (e.key === 'Enter') update('q', (e.target as HTMLInputElement).value) }}
      />

      {/* Divider */}
      <div style={{ width: 1, height: 24, background: '#1E2330', flexShrink: 0 }} />

      {/* Custom dark selects */}
      <CustomSelect
        options={FUNCTION_CATEGORIES.map((v) => ({ value: v, label: v }))}
        value={val('function')}
        onChange={(v) => update('function', v)}
        placeholder="Any function"
        width={140}
      />
      <CustomSelect
        options={VERTICALS.map((v) => ({ value: v, label: v }))}
        value={val('vertical')}
        onChange={(v) => update('vertical', v)}
        placeholder="Any vertical"
        width={140}
      />
      <CustomSelect
        options={SENIORITIES.map((v) => ({ value: v, label: v }))}
        value={val('seniority')}
        onChange={(v) => update('seniority', v)}
        placeholder="Any seniority"
        width={130}
      />
      <CustomSelect
        options={REMOTE_STATUSES.map((v) => ({ value: v, label: v }))}
        value={val('remote')}
        onChange={(v) => update('remote', v)}
        placeholder="Any location"
        width={130}
      />

      {/* Divider */}
      <div style={{ width: 1, height: 24, background: '#1E2330', flexShrink: 0 }} />

      {/* Numeric inputs */}
      <input key={`salaryFloor-${urlKey}`} type="number" placeholder="min $"   className="no-spin" style={{ ...INPUT_BASE, width: 80 }} min={0} defaultValue={val('salaryFloor')} onFocus={onFocus} onBlur={(e) => { onBlur(e); update('salaryFloor', e.target.value) }} />
      <input key={`matchMin-${urlKey}`}    type="number" placeholder="match ≥" className="no-spin" style={{ ...INPUT_BASE, width: 80 }} min={0} defaultValue={val('matchMin')}    onFocus={onFocus} onBlur={(e) => { onBlur(e); update('matchMin',    e.target.value) }} />

      {!hidePostedWithin && (
        <CustomSelect
          options={[
            { value: '1d',  label: 'Last 24h' },
            { value: '7d',  label: 'Last 7 days' },
            { value: '30d', label: 'Last 30 days' },
          ]}
          value={val('postedWithin')}
          onChange={(v) => update('postedWithin', v)}
          placeholder="Any date"
          width={120}
        />
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
