// Auth gate — redirects to /login if no session, except for public paths
// (/login, /auth/callback). Also refreshes the Supabase session cookie on
// every request so `cookies().set(...)` calls from Server Components
// don't silently drop (see lib/supabase/server.ts).
//
// The matcher at the bottom skips Next internals and static assets so we
// don't re-authenticate on every font / image request.

import { createServerClient } from '@supabase/ssr'
import { type NextRequest, NextResponse } from 'next/server'

const PUBLIC_PATHS = ['/login', '/auth/callback']

/**
 * Audit N-C3: CSP is computed from RUNTIME env so a preview deploy with
 * a different Supabase project picks up its host without a rebuild.
 *
 * Notes on the directive list:
 *   - `worker-src 'self' blob:` — Supabase Realtime and Next instrumentation
 *     spawn workers from `blob:` URLs that the default `script-src` fallback
 *     would block.
 *   - `connect-src` includes `wss://` for Supabase Realtime; `api.github.com`
 *     is intentionally OMITTED — the browser only ever talks to our own
 *     /api/* routes, never to GitHub directly.
 *   - `unsafe-inline` is required on script-src + style-src for now: Next
 *     14's hydration markers and Sonner toast inject inline styles inside
 *     shadow DOM. Migrating to nonce-based CSP is a deliberate breaking
 *     change; see CSP comment for the work item.
 */
function buildCsp(): string {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? ''
  const supabaseHost = supabaseUrl.replace(/^https?:\/\//, '').replace(/\/$/, '')
  const supabaseOrigin = supabaseHost ? `https://${supabaseHost} wss://${supabaseHost}` : ''
  const directives = [
    "default-src 'self'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "object-src 'none'",
    `img-src 'self' data: blob: ${supabaseHost ? `https://${supabaseHost}` : ''}`.trim(),
    `connect-src 'self' ${supabaseOrigin}`.trim(),
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self' data: https://fonts.gstatic.com",
    "worker-src 'self' blob:",
    "media-src 'self'",
  ]
  return directives.join('; ')
}

export async function middleware(request: NextRequest) {
  let response = NextResponse.next({ request })

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll()
        },
        setAll(cookiesToSet) {
          // Audit H8: forward options on the request-side write too.
          // The previous version dropped Path/HttpOnly/Secure/SameSite/Max-Age
          // on `request.cookies.set(name, value)`, so the rebuilt
          // `NextResponse.next({ request })` saw incomplete cookie state.
          // This is the canonical Supabase SSR template.
          cookiesToSet.forEach(({ name, value, options }) =>
            request.cookies.set({ name, value, ...options })
          )
          response = NextResponse.next({ request })
          cookiesToSet.forEach(({ name, value, options }) =>
            response.cookies.set(name, value, options)
          )
        },
      },
    }
  )

  // IMPORTANT: getUser() revalidates with Supabase; getSession() does not.
  // Use getUser() in the auth gate so a revoked session can't linger.
  const {
    data: { user },
  } = await supabase.auth.getUser()

  const { pathname } = request.nextUrl
  const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p))

  if (!user && !isPublic) {
    const url = request.nextUrl.clone()
    url.pathname = '/login'
    return NextResponse.redirect(url)
  }

  if (user && pathname === '/login') {
    const url = request.nextUrl.clone()
    url.pathname = '/'
    return NextResponse.redirect(url)
  }

  // Apply runtime-computed CSP. Done here so the policy follows the
  // Supabase project URL at request time, not build time.
  response.headers.set('Content-Security-Policy', buildCsp())

  return response
}

export const config = {
  // Skip Next internals + static assets. The negative lookahead keeps
  // image / font / favicon requests out of the auth check.
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|woff|woff2|ttf|otf)$).*)',
  ],
}
