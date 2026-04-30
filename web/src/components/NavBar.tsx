'use client'

// NavBar — Bloomberg-terminal dark redesign.
// Client component so we can read usePathname() for active-link highlighting.
// Email + sign-out live in the right zone; hex icon + wordmark in the left.

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'

const LINKS: Array<{ href: string; label: string }> = [
  { href: '/',         label: 'Today'    },
  { href: '/week',     label: 'Week'     },
  { href: '/archive',  label: 'Archive'  },
  { href: '/apply',    label: 'Apply'    },
  { href: '/resume',   label: 'CV'       },
  { href: '/settings', label: 'Settings' },
]

export function NavBar({ email }: { email?: string | null }) {
  const pathname = usePathname()
  const router   = useRouter()

  async function signOut() {
    const supabase = createClient()
    await supabase.auth.signOut()
    router.push('/login')
    router.refresh()
  }

  return (
    <header
      className="fixed top-0 left-0 right-0 z-50 h-14 flex items-center px-6 gap-6"
      style={{
        background: 'rgba(10,12,16,0.95)',
        backdropFilter: 'blur(12px)',
        borderBottom: '1px solid #1E2330',
      }}
    >
      {/* ── Left: icon + wordmark ─────────────────────────────────── */}
      <Link href="/" className="flex items-center gap-2 shrink-0">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
          <path
            d="M9 1.5L16 5.25V12.75L9 16.5L2 12.75V5.25L9 1.5Z"
            stroke="#00D4FF"
            strokeWidth="1.5"
            fill="rgba(0,212,255,0.08)"
            strokeLinejoin="round"
          />
          <circle cx="9" cy="9" r="2" fill="#00D4FF" opacity="0.7" />
        </svg>
        <span
          className="font-heading font-bold text-base"
          style={{ color: '#E8ECF0', letterSpacing: '-0.02em' }}
        >
          job-agent
        </span>
      </Link>

      {/* ── Center: nav links ────────────────────────────────────── */}
      <nav className="flex items-center flex-1 justify-center">
        {LINKS.map((l) => {
          const isActive =
            l.href === '/'
              ? pathname === '/'
              : pathname.startsWith(l.href)
          return (
            <Link
              key={l.href}
              href={l.href}
              className="relative flex items-center h-14 px-3.5 text-[13px] font-medium transition-colors duration-150"
              style={{
                color: isActive ? '#E8ECF0' : '#6B7A99',
                letterSpacing: '0.01em',
                borderBottom: isActive ? '2px solid #00D4FF' : '2px solid transparent',
              }}
              onMouseEnter={(e) => {
                if (!isActive)
                  (e.currentTarget as HTMLElement).style.color = '#A0AABB'
              }}
              onMouseLeave={(e) => {
                if (!isActive)
                  (e.currentTarget as HTMLElement).style.color = '#6B7A99'
              }}
            >
              {l.label}
            </Link>
          )
        })}
      </nav>

      {/* ── Right: email + sign out ───────────────────────────────── */}
      <div className="flex items-center gap-3 shrink-0">
        {email && (
          <span className="hidden sm:inline font-mono text-[11px]" style={{ color: '#6B7A99' }}>
            {email}
          </span>
        )}
        {email && (
          <button
            onClick={signOut}
            className="font-mono text-[12px] font-medium rounded-[6px] px-3 py-[5px] transition-colors duration-150"
            style={{
              background: 'transparent',
              border: '1px solid #252D40',
              color: '#A0AABB',
            }}
            onMouseEnter={(e) => {
              const el = e.currentTarget as HTMLButtonElement
              el.style.borderColor = '#6B7A99'
              el.style.color       = '#E8ECF0'
            }}
            onMouseLeave={(e) => {
              const el = e.currentTarget as HTMLButtonElement
              el.style.borderColor = '#252D40'
              el.style.color       = '#A0AABB'
            }}
          >
            Sign out
          </button>
        )}
      </div>
    </header>
  )
}
