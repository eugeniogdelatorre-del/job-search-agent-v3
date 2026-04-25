'use client'

// Magic-link sign-in — dark terminal redesign.
// Single-user: only eugeniogdelatorre@gmail.com can sign in (enforced DB-side).

import { useState } from 'react'
import { createClient } from '@/lib/supabase/client'

type Status = 'idle' | 'sending' | 'sent' | 'error'

export default function LoginPage() {
  const [email,    setEmail]    = useState('')
  const [status,   setStatus]   = useState<Status>('idle')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setStatus('sending')
    setErrorMsg(null)
    try {
      const supabase = createClient()
      const { error } = await supabase.auth.signInWithOtp({
        email,
        options: { emailRedirectTo: `${location.origin}/auth/callback` },
      })
      if (error) throw error
      setStatus('sent')
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Unknown error')
      setStatus('error')
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div
        className="w-full max-w-sm rounded-[12px] p-8 space-y-6"
        style={{ background: '#0F1117', border: '1px solid #1E2330' }}
      >
        {/* Logo */}
        <div className="flex items-center gap-2 justify-center">
          <svg width="20" height="20" viewBox="0 0 18 18" fill="none">
            <path d="M9 1.5L16 5.25V12.75L9 16.5L2 12.75V5.25L9 1.5Z" stroke="#00D4FF" strokeWidth="1.5" fill="rgba(0,212,255,0.08)" strokeLinejoin="round"/>
            <circle cx="9" cy="9" r="2" fill="#00D4FF" opacity="0.7"/>
          </svg>
          <span className="font-heading font-bold text-lg" style={{ color: '#E8ECF0', letterSpacing: '-0.02em' }}>
            job-agent
          </span>
        </div>

        {status === 'sent' ? (
          <div className="text-center space-y-2">
            <p className="font-mono text-[13px]" style={{ color: '#E8ECF0' }}>Check your inbox</p>
            <p className="font-mono text-[11px]" style={{ color: '#6B7A99' }}>
              Magic link sent to <span style={{ color: '#A0AABB' }}>{email}</span>
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label className="font-mono text-[10px] uppercase tracking-widest" style={{ color: '#3A4460' }}>
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                className="w-full rounded-[6px] px-3 py-2.5 font-mono text-[12px] focus:outline-none"
                style={{
                  background:   'rgba(255,255,255,0.03)',
                  border:       '1px solid #252D40',
                  color:        '#E8ECF0',
                }}
                onFocus={(e)  => { e.target.style.borderColor = '#00D4FF'; e.target.style.boxShadow = '0 0 0 2px rgba(0,212,255,0.15)' }}
                onBlur={(e)   => { e.target.style.borderColor = '#252D40'; e.target.style.boxShadow = 'none' }}
              />
            </div>

            {errorMsg && (
              <p className="font-mono text-[11px]" style={{ color: '#F87171' }}>{errorMsg}</p>
            )}

            <button
              type="submit"
              disabled={status === 'sending'}
              className="w-full rounded-[7px] py-2.5 font-mono text-[12px] font-semibold transition-opacity"
              style={{
                background: '#00D4FF',
                color:      '#000',
                opacity:    status === 'sending' ? 0.7 : 1,
              }}
            >
              {status === 'sending' ? 'Sending…' : 'Send magic link →'}
            </button>
          </form>
        )}
      </div>
    </div>
  )
}
