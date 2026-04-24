// Server-side Supabase client for Server Components, Route Handlers,
// and Server Actions. Uses anon key + cookies so RLS policies still
// see the authenticated user. For service-role writes (bypass RLS),
// construct a separate client inline in an API route with
// SUPABASE_SERVICE_KEY — do not use this helper.

import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'

export function createClient() {
  const cookieStore = cookies()

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
}
