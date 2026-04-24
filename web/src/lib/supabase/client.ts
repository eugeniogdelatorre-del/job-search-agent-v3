// Browser-side Supabase client for Client Components. Uses the anon
// key, which is safe to expose — RLS policies enforce access control
// server-side. The session is stored in cookies (via @supabase/ssr)
// so the server and client stay in sync across navigation.

import { createBrowserClient } from '@supabase/ssr'

export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  )
}
