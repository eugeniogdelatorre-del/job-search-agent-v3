'use client'

// Fully-custom dark dropdown. Replaces native <select> so the popup list
// renders in our design colors on every browser/OS (native <select> popups
// can't be CSS-forced dark cross-platform).

import { useState, useRef, useEffect } from 'react'

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
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleOut(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleOut)
    return () => document.removeEventListener('mousedown', handleOut)
  }, [])

  const label = value
    ? (options.find((o) => o.value === value)?.label ?? value)
    : placeholder

  const isActive = open || focused

  return (
    <div ref={ref} style={{ position: 'relative', width }}>
      <button
        type="button"
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
        <div style={{
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
        }}>
          {[{ value: '', label: placeholder }, ...options].map((opt) => {
            const isSel = opt.value === value
            return (
              <div
                key={opt.value}
                onClick={() => { onChange(opt.value); setOpen(false) }}
                style={{
                  padding:    '7px 12px',
                  fontFamily: 'var(--font-mono)',
                  fontSize:   '11px',
                  color:      isSel ? '#00D4FF' : opt.value === '' ? '#6B7A99' : '#E8ECF0',
                  background: isSel ? 'rgba(0,212,255,0.08)' : 'transparent',
                  cursor:     'pointer',
                  transition: 'background 0.1s',
                }}
                onMouseEnter={(e) => {
                  if (!isSel) (e.currentTarget as HTMLElement).style.background = '#141820'
                }}
                onMouseLeave={(e) => {
                  if (!isSel) (e.currentTarget as HTMLElement).style.background = 'transparent'
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
