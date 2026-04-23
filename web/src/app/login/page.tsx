'use client'

// Magic-link sign-in. Single-user app, so the only legitimate address is
// eugeniogdelatorre@gmail.com — enforced server-side by the SQL trigger
// in §2 of the plan. Typing any other email here will succeed at the
// client layer (Supabase confirms the OTP send) but the actual signup
// will be rejected in the DB, and the magic link will 403 on callback.
// That's fine — it's belt-and-braces single-user protection.

import { useState } from 'react'
import { createClient } from '@/lib/supabase/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

type Status = 'idle' | 'sending' | 'sent' | 'error'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setStatus('sending')
    setErrorMsg(null)

    const supabase = createClient()
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: {
        emailRedirectTo: `${window.location.origin}/auth/callback`,
        // Don't auto-create a new user on signin — the SQL trigger
        // blocks unauthorized emails, but this is a cleaner UX for
        // them (no "check your email" for a link that'll never work).
        shouldCreateUser: true,
      },
    })

    if (error) {
      setErrorMsg(error.message)
      setStatus('error')
    } else {
      setStatus('sent')
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Sign in</CardTitle>
          <CardDescription>
            Job search agent — magic link auth.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {status === 'sent' ? (
            <div className="space-y-2 text-sm">
              <p>Check your inbox — we sent a magic link to <b>{email}</b>.</p>
              <p className="text-muted-foreground">
                The link expires in 60 minutes.
              </p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="flex flex-col gap-3">
              <Input
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={status === 'sending'}
                autoComplete="email"
              />
              <Button type="submit" disabled={status === 'sending' || !email}>
                {status === 'sending' ? 'Sending…' : 'Send magic link'}
              </Button>
              {errorMsg ? (
                <p className="text-sm text-destructive">{errorMsg}</p>
              ) : null}
            </form>
          )}
        </CardContent>
      </Card>
    </main>
  )
}
