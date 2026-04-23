// Root layout. Uses Inter (Next 14-compatible) mapped to --font-sans
// via the Tailwind config. Toaster is mounted here so any Client
// Component can fire toast() without wiring it up at page level.

import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import { cn } from '@/lib/utils'
import './globals.css'
import { Toaster } from '@/components/ui/sonner'

const inter = Inter({ subsets: ['latin'], variable: '--font-sans' })

export const metadata: Metadata = {
  title: 'Job Search Agent',
  description: 'Web3 job search — scraped, classified, scored.',
}

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={cn('font-sans', inter.variable)}>
      <body className="antialiased min-h-screen bg-background text-foreground">
        {children}
        <Toaster />
      </body>
    </html>
  )
}
