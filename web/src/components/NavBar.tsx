// Minimal shared top nav. Phases 6–9 will expand this (Apply, Resume,
// Tune, Settings). For Phase 5 we only expose the three job views.

import Link from 'next/link'
import SignOutButton from '@/components/SignOutButton'

const LINKS: Array<{ href: string; label: string }> = [
  { href: '/', label: 'Today' },
  { href: '/week', label: 'Week' },
  { href: '/archive', label: 'Archive' },
]

export function NavBar({ email }: { email?: string | null }) {
  return (
    <header className="sticky top-0 z-10 border-b bg-background/85 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4">
        <Link href="/" className="font-semibold">
          job-agent
        </Link>
        <nav className="flex items-center gap-1">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3">
          {email && (
            <span className="hidden text-xs text-muted-foreground sm:inline">
              {email}
            </span>
          )}
          <SignOutButton />
        </div>
      </div>
    </header>
  )
}
