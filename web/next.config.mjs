// Audit M7 + N-C3 baseline security headers.
//
// Only headers that DON'T depend on runtime env are emitted from
// next.config.mjs. CSP is emitted from middleware.ts instead, because
// `next.config.mjs` only sees env vars at BUILD time — a preview deploy
// with a missing NEXT_PUBLIC_SUPABASE_URL would have an empty
// `connect-src` directive baked in for the lifetime of that build, and
// Supabase calls would be blocked even if the env var is set at runtime.
// Middleware reads runtime env on every request, so the policy is always
// in sync with whichever Supabase project the deploy points at.

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'Strict-Transport-Security', value: 'max-age=31536000; includeSubDomains' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'Referrer-Policy', value: 'same-origin' },
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=(), interest-cohort=()',
          },
          // CSP is set in src/middleware.ts (runtime env). See header
          // comment there for the full directive list.
        ],
      },
    ]
  },
}

export default nextConfig
