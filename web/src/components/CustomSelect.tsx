'use client'

// Fully-custom dark dropdown. Replaces native <select> so the popup list
// renders in our design colors on every browser/OS (native <select> popups
// can't be CSS-forced dark cross-platform).
//
// Audit N-M5: keyboard + ARIA support added.
//   - ArrowDown / ArrowUp move highlight; opens the menu when closed.
//   - Enter commits the highlighted option.
//   - Escape closes the menu and refocuses the trigger.
//   - Home/End jump to first/last option.
//   - Trigger gets role="combobox" + aria-expanded + aria-controls.
//   - Options get role="option" + aria-selected.

import { useEffect, useId, useRef, useState } from 'react'

type Option = { value: string; label: string }

type Props = {
  options:     Option[]
  value:       string
  onChange:    (val: string) => void
  placeholder: string
  width?:      number | string
}

const TRIGGER: React.CSSProperties = {
  display:        'inline-flex',
  alignItems:     'center',
  justifyContent: 'space-between',
  gap:            6,
  background:     'rgba(255,255,255,0.03)',
  border:         '1px solid #1E2330',
  borderRadius:   '6px',
  color:          '#E8ECF0',
  fontFamily:     'var(--font-mono)',
  fontSize:       '11px',
  padding:        '0 10px',
  height:         '34px',
  outline:        'none',
  cursor:         'pointer',
  transition:     'border-color 0.15s, box-shadow 0.15s',
  userSelect:     'none',
  whiteSpace:     'nowrap',
}

export function CustomSelect({ options, value, onChange, placeholder, width }: Props) {
  const [open,    setOpen]    = useState(false)
  const [focused, setFocused] = useState(false)
  const [highlightIdx, setHighlightIdx] = useState<number>(-1)
  const ref = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const listboxId = useId()

  // Empty-row + real options. Built once per render but small.
  const items: Option[] = [{ value: '', label: placeholder }, ...options]

  // Sync highlight to current selection when opening.
  useEffect(() => {
    if (open) {
      const idx = items.findIndex((o) => o.value === value)
      setHighlightIdx(idx >= 0 ? idx : 0)
    } else {
      setHighlightIdx(-1)
    }
    // items is recomputed each render but its shape is stable per options/value
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, value])

  useEffect(() => {
    function handleOut(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleOut)
    return () => document.removeEventListener('mousedown', handleOut)
  }, [])

  function commit(idx: number) {
    const opt = items[idx]
    if (!opt) return
    onChange(opt.value)
    setOpen(false)
    triggerRef.current?.focus()
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    // Open on ArrowDown/ArrowUp/Enter/Space from a closed trigger.
    if (!open) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        setOpen(true)
      }
      return
    }
    if (e.key === 'Escape') {
      e.preventDefault()
      setOpen(false)
      triggerRef.current?.focus()
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlightIdx((i) => Math.min(items.length - 1, i + 1))
      return
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlightIdx((i) => Math.max(0, i - 1))
      return
    }
    if (e.key === 'Home') {
      e.preventDefault()
      setHighlightIdx(0)
      return
    }
    if (e.key === 'End') {
      e.preventDefault()
      setHighlightIdx(items.length - 1)
      return
    }
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      if (highlightIdx >= 0) commit(highlightIdx)
      return
    }
    if (e.key === 'Tab') {
      // Let Tab move focus naturally; close the menu so the next focus
      // target isn't behind an overlay.
      setOpen(false)
    }
  }

  const label = value
    ? (options.find((o) => o.value === value)?.label ?? value)
    : placeholder

  const isActive = open || focused

  return (
    <div ref={ref} style={{ position: 'relative', width }} onKeyDown={onKeyDown}>
      <button
        ref={triggerRef}
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        onClick={() => setOpen((o) => !o)}
        onFocus={() => setFocused(true)}
        onBlur={() => { setFocused(false) }}
        style={{
          ...TRIGGER,
          width:       '100%',
          borderColor: isActive ? '#00D4FF' : '#1E2330',
          boxShadow:   isActive ? '0 0 0 2px rgba(0,212,255,0.15)' : 'none',
          color:       value ? '#E8ECF0' : '#6B7A99',
        }}
      >
        <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', textAlign: 'left' }}>
          {label}
        </span>
        <svg
          width="10" height="6" viewBox="0 0 10 6" fill="none"
          style={{
            flexShrink: 0,
            transform:  open ? 'rotate(180deg)' : undefined,
            transition: 'transform 0.15s',
          }}
        >
          <path
            d="M1 1l4 4 4-4"
            stroke="#6B7A99"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      {open && (
        <div
          id={listboxId}
          role="listbox"
          style={{
            position:     'absolute',
            top:          'calc(100% + 4px)',
            left:         0,
            minWidth:     '100%',
            background:   '#0F1117',
            border:       '1px solid #252D40',
            borderRadius: '6px',
            zIndex:       200,
            boxShadow:    '0 8px 24px rgba(0,0,0,0.6)',
            overflow:     'hidden',
            maxHeight:    '280px',
            overflowY:    'auto',
          }}
        >
          {items.map((opt, idx) => {
            const isSel = opt.value === value
            const isHighlighted = idx === highlightIdx
            return (
              <div
                key={opt.value}
                role="option"
                aria-selected={isSel}
                onMouseEnter={() => setHighlightIdx(idx)}
                onClick={() => commit(idx)}
                style={{
                  padding:    '7px 12px',
                  fontFamily: 'var(--font-mono)',
                  fontSize:   '11px',
                  color:      isSel ? '#00D4FF' : opt.value === '' ? '#6B7A99' : '#E8ECF0',
                  background: isHighlighted
                    ? (isSel ? 'rgba(0,212,255,0.14)' : '#141820')
                    : (isSel ? 'rgba(0,212,255,0.08)' : 'transparent'),
                  cursor:     'pointer',
                  transition: 'background 0.1s',
                }}
              >
                {opt.label}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
