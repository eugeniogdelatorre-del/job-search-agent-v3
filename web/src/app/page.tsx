// Minimal authed home. Middleware already redirects unauth'd users to
// /login; we call getUser() again here to get the email for the greeting
// (and as belt-and-braces in case middleware ever gets misconfigured).
// Real job views come online in Phase 5.

import { createClient } from '@/lib/supabase/server'
import { redirect } from 'next/navigation'
import SignOutButton from '@/components/SignOutButton'

export default async function Home() {
  const supabase = createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()

  if (!user) {
    redirect('/login')
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <div className="flex flex-col items-center gap-4 text-center">
        <h1 className="text-2xl font-semibold">Hello, {user.email}</h1>
        <p className="text-sm text-muted-foreground max-w-sm">
          Job search agent v3 is online. Job views come in Phase 5.
        </p>
        <SignOutButton />
      </div>
    </main>
  )
}
