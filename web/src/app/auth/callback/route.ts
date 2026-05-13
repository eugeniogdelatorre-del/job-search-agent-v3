// Handles the magic-link redirect from Supabase. Supabase sends the user
// here with `?code=...`; we exchange it for a session cookie and then
// bounce them to `?next=...` (or /, the default).
//
// If the email was rejected by the SQL trigger (unauthorized address),
// the exchange fails and we send them back to /login with an error flag
// so the form can show a hint.

import { createClient } from '@/lib/supabase/server'
import { NextResponse, type NextRequest } from 'next/server'

// Audit L19: be explicit about runtime + dynamic to match sibling routes.
// auth callback reads cookies and exchanges a code with Supabase —
// must NOT be statically optimised.
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Constrain `next` to a same-origin relative path so the callback can't
 * be turned into an open redirect. Rejects:
 *   - absolute / scheme-bearing URLs ("https://evil.com", "javascript:…")
 *   - protocol-relative bypasses ("//evil.com", "/\\evil.com")
 *   - URL-encoded protocol-relative bypasses ("/%2F%2Fevil.com")
 *   - control chars and newlines (header smuggling)
 *   - over-long values
 *
 * Audit N-C2: we now also resolve the candidate path against the request
 * origin and reject any resolution that ends up on a different origin —
 * the most robust check, since the browser's redirect-following will
 * normalize URL-encoded slashes back to "/" before navigating. Falls
 * back to "/" on any uncertainty.
 */
function safeNextPath(raw: string | null, requestUrl: string): string {
  if (!raw) return '/'
  if (raw.length > 512) return '/'
  if (!raw.startsWith('/')) return '/'
  if (raw.startsWith('//') || raw.startsWith('/\\')) return '/'
  // Defeat URL-encoded protocol-relative bypass: a value like
  // "/%2F%2Fevil.com" decodes to "//evil.com" before the browser
  // follows the redirect. Reject on any decoded leading "//" / "/\\".
  let decoded = ''
  try {
    decoded = decodeURIComponent(raw)
  } catch {
    return '/'  // malformed % escape
  }
  if (decoded.startsWith('//') || decoded.startsWith('/\\')) return '/'
  // eslint-disable-next-line no-control-regex
  if (/[\x00-\x1f\x7f]/.test(decoded)) return '/'
  // Same-origin guarantee: resolve the candidate against the request URL
  // and verify the origin matches. URL parsing also blocks any sneaky
  // scheme that slipped past the startsWith('/') check (e.g. some clients
  // accept "/\\\\foo" → file:// on Windows).
  try {
    const base = new URL(requestUrl)
    const target = new URL(raw, base)
    if (target.origin !== base.origin) return '/'
  } catch {
    return '/'
  }
  return raw
}

export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url)
  const code = searchParams.get('code')
  const next = safeNextPath(searchParams.get('next'), request.url)

  if (code) {
    const supabase = await createClient()
    const { error } = await supabase.auth.exchangeCodeForSession(code)
    if (!error) {
      return NextResponse.redirect(`${origin}${next}`)
    }
    // Fall through on error.
  }

  return NextResponse.redirect(`${origin}/login?error=auth_callback_failed`)
}
