// Root layout. Loads IBM Plex Mono + Syne + Inter via next/font/google.
// Applies the `dark` class permanently — this app has no light mode.
// NavBar is mounted here so every route (including /apply, /settings
// that previously lacked it) gets consistent navigation without per-page
// duplication. A pt-14 wrapper offsets content below the 56px sticky bar.

import type { Metadata } from 'next'
import { IBM_Plex_Mono, Syne, Inter } from 'next/font/google'
import { cn } from '@/lib/utils'
import { createClient } from '@/lib/supabase/server'
import { NavBar } from '@/components/NavBar'
import { Toaster } from '@/components/ui/sonner'
import './globals.css'

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-mono',
})

const syne = Syne({
  subsets: ['latin'],
  weight: ['600', '700', '800'],
  variable: '--font-heading',
})

const inter = Inter({
  subsets: ['latin'],
  weight: ['400', '500'],
  variable: '--font-body',
})

export const metadata: Metadata = {
  title: 'job-agent',
  description: 'Web3 job search — scraped, classified, scored.',
}

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const supabase = createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()

  return (
    <html
      lang="en"
      className={cn(
        'dark font-body',
        ibmPlexMono.variable,
        syne.variable,
        inter.variable
      )}
    >
      <body className="antialiased min-h-screen bg-background text-foreground">
        <NavBar email={user?.email} />
        {/* pt-14 = 56px — clears the sticky NavBar */}
        <div className="pt-14">
          {children}
        </div>
        <Toaster />
      </body>
    </html>
  )
}
