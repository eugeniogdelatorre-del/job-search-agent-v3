// Server-side Supabase client for Server Components, Route Handlers,
// and Server Actions. Uses anon key + cookies so RLS policies still
// see the authenticated user. For service-role writes (bypass RLS),
// construct a separate client inline in an API route with
// SUPABASE_SERVICE_KEY — do not use this helper.
//
// Audit H7 + H9 (2026-05-12):
//   H7 — `cookies()` was synchronous in Next 14 but became async in
//        Next 15. Awaiting it here works on both versions (await of a
//        non-Promise is a no-op) and survives the upgrade with no
//        further change.
//   H9 — `createClient` and `getCurrentUser` are wrapped in React's
//        `cache()` so multiple calls inside the same request (server
//        component → child component → API route → jobs-query) share
//        ONE constructed client and ONE Supabase auth round-trip
//        instead of constructing N clients and making N getUser() HTTPS
//        calls to Supabase.

import { cache } from 'react'
import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'

export const createClient = cache(async () => {
  const cookieStore = await cookies()

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll()
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options)
            )
          } catch {
            // Called from a Server Component — ignore. The middleware
            // refreshes the session cookie on every request, so losing
            // this write here is fine.
          }
        },
      },
    }
  )
})

/**
 * Per-request memoised auth user. Use instead of `supabase.auth.getUser()`
 * when you only need the user object — avoids the extra network round-trip
 * when multiple call sites in the same request need the user.
 *
 * Returns null for anon requests.
 */
export const getCurrentUser = cache(async () => {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  return user
})
