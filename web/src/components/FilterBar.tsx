'use client'

// FilterBar — pushes changes into the URL search params so the server
// component re-reads them and re-queries. No client-side state store.
//
// Only the filters listed in plan §6 Phase 5. Posted-within defaults to
// page-level defaults (e.g. /week always scopes to 7d via its own cutoff),
// but the user can tighten on any page using this control.

import { useRouter, usePathname, useSearchParams } from 'next/navigation'
import { useTransition } from 'react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import {
  FUNCTION_CATEGORIES,
  REMOTE_STATUSES,
  SENIORITIES,
  VERTICALS,
} from '@/types/db'
import { FILTER_KEYS } from '@/lib/filters'

type Props = {
  /** Hide the postedWithin control when the page is already scoped (e.g. /week). */
  hidePostedWithin?: boolean
}

export function FilterBar({ hidePostedWithin }: Props) {
  const router = useRouter()
  const pathname = usePathname()
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
    startTransition(() => {
      router.replace(pathname, { scroll: false })
    })
  }

  const val = (k: string) => searchParams.get(k) ?? ''
  const hasFilters = FILTER_KEYS.some((k) => searchParams.get(k))

  const selectCls =
    'h-9 rounded-md border border-input bg-background px-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring'

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-card p-3">
      <Input
        type="search"
        placeholder="Search title / company"
        className="h-9 w-full max-w-xs"
        defaultValue={val('q')}
        onKeyDown={(e) => {
          if (e.key === 'Enter') update('q', (e.target as HTMLInputElement).value)
        }}
      />

      <select
        className={selectCls}
        value={val('function')}
        onChange={(e) => update('function', e.target.value)}
      >
        <option value="">Any function</option>
        {FUNCTION_CATEGORIES.map((v) => (
          <option key={v} value={v}>
            {v}
          </option>
        ))}
      </select>

      <select
        className={selectCls}
        value={val('vertical')}
        onChange={(e) => update('vertical', e.target.value)}
      >
        <option value="">Any vertical</option>
        {VERTICALS.map((v) => (
          <option key={v} value={v}>
            {v}
          </option>
        ))}
      </select>

      <select
        className={selectCls}
        value={val('seniority')}
        onChange={(e) => update('seniority', e.target.value)}
      >
        <option value="">Any seniority</option>
        {SENIORITIES.map((v) => (
          <option key={v} value={v}>
            {v}
          </option>
        ))}
      </select>

      <select
        className={selectCls}
        value={val('remote')}
        onChange={(e) => update('remote', e.target.value)}
      >
        <option value="">Any location</option>
        {REMOTE_STATUSES.map((v) => (
          <option key={v} value={v}>
            {v}
          </option>
        ))}
      </select>

      <Input
        type="number"
        placeholder="Min salary $"
        className="h-9 w-32"
        defaultValue={val('salaryFloor')}
        onBlur={(e) => update('salaryFloor', e.target.value)}
      />

      <Input
        type="number"
        placeholder="Rule score ≥"
        className="h-9 w-32"
        min={0}
        max={100}
        defaultValue={val('scoreMin')}
        onBlur={(e) => update('scoreMin', e.target.value)}
      />

      <Input
        type="number"
        placeholder="Match % ≥"
        className="h-9 w-28"
        min={0}
        max={100}
        defaultValue={val('matchMin')}
        onBlur={(e) => update('matchMin', e.target.value)}
      />

      {!hidePostedWithin && (
        <select
          className={selectCls}
          value={val('postedWithin')}
          onChange={(e) => update('postedWithin', e.target.value)}
        >
          <option value="">Any date</option>
          <option value="1d">Last 24h</option>
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
        </select>
      )}

      {hasFilters && (
        <Button
          variant="ghost"
          size="sm"
          onClick={reset}
          disabled={isPending}
        >
          Clear
        </Button>
      )}
    </div>
  )
}
