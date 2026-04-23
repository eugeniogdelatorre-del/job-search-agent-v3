// Handles the magic-link redirect from Supabase. Supabase sends the user
// here with `?code=...`; we exchange it for a session cookie and then
// bounce them to `?next=...` (or /, the default).
//
// If the email was rejected by the SQL trigger (unauthorized address),
// the exchange fails and we send them back to /login with an error flag
// so the form can show a hint.

import { createClient } from '@/lib/supabase/server'
import { NextResponse, type NextRequest } from 'next/server'

export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url)
  const code = searchParams.get('code')
  const next = searchParams.get('next') ?? '/'

  if (code) {
    const supabase = createClient()
    const { error } = await supabase.auth.exchangeCodeForSession(code)
    if (!error) {
      return NextResponse.redirect(`${origin}${next}`)
    }
    // Fall through on error.
  }

  return NextResponse.redirect(`${origin}/login?error=auth_callback_failed`)
}
