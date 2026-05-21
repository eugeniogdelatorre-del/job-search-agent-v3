// GET /api/export?format=csv|json|notion&scopeSinceDays=60&<filters>
//
// Exports the filtered job list. format=notion emits a CSV with the
// column set Notion's "Import CSV" happily maps to properties.
// Filters are the same search params /archive uses (see lib/filters.ts).

import { NextRequest, NextResponse } from 'next/server'
import { queryJobs } from '@/lib/jobs-query'
import { parseFilters } from '@/lib/filters'
import { createClient, getCurrentUser } from '@/lib/supabase/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const MAX_ROWS = 2000

function csvEscape(v: unknown): string {
  if (v === null || v === undefined) return ''
  let s = String(v)
  // H1-new (2026-05-20): formula-injection guard (CWE-1236). Excel, Google
  // Sheets, and LibreOffice execute cells whose first character is =, +, -,
  // @, tab, or CR as formulas. Prefix with a single quote so the spreadsheet
  // treats them as literal text (OWASP recommendation). The quote is hidden
  // from display in most spreadsheet apps.
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`
  return s
}

export async function GET(req: NextRequest) {
  await createClient()
  const user = await getCurrentUser()
  if (!user) return NextResponse.json({ error: 'not authenticated' }, { status: 401 })

  const sp = req.nextUrl.searchParams
  const format = (sp.get('format') ?? 'csv').toLowerCase()
  const scopeSinceDays = Number(sp.get('scopeSinceDays') ?? '60')

  const filterObj: Record<string, string> = {}
  sp.forEach((v, k) => {
    filterObj[k] = v
  })
  const filters = parseFilters(filterObj)

  const { rows, error } = await queryJobs({
    filters,
    scopeSinceDays: Number.isFinite(scopeSinceDays) ? scopeSinceDays : 60,
    limit: MAX_ROWS,
  })
  if (error) {
    return NextResponse.json({ error }, { status: 500 })
  }

  if (format === 'json') {
    return NextResponse.json({ rows })
  }

  // CSV (default) and Notion (same columns, different header casing).
  const notion = format === 'notion'
  const headers = notion
    ? [
        'Name',
        'Company',
        'Match',
        'Rule Score',
        'Function',
        'Vertical',
        'Seniority',
        'Remote',
        'Salary Min',
        'Salary Max',
        'Location',
        'Source',
        'Apply URL',
        'First Seen',
        'Verdict',
      ]
    : [
        'title',
        'company',
        'match_score',
        'score_total',
        'function_category',
        'vertical',
        'seniority',
        'remote_status',
        'salary_min_usd',
        'salary_max_usd',
        'location',
        'source',
        'apply_url',
        'first_seen_at',
        'verdict_one_liner',
      ]

  const lines: string[] = [headers.map(csvEscape).join(',')]
  for (const r of rows) {
    const score = r.job_scores?.[0]
    lines.push(
      [
        r.title,
        r.company ?? '',
        score?.match_score ?? '',
        r.score_total ?? '',
        r.function_category ?? '',
        r.vertical ?? '',
        r.seniority ?? '',
        r.remote_status ?? '',
        r.salary_min_usd ?? '',
        r.salary_max_usd ?? '',
        r.location ?? '',
        r.source,
        r.apply_url ?? r.source_url ?? '',
        r.first_seen_at,
        score?.verdict_one_liner ?? '',
      ]
        .map(csvEscape)
        .join(',')
    )
  }

  const body = lines.join('\n') + '\n'
  const filename = `jobs-${new Date().toISOString().slice(0, 10)}${
    notion ? '-notion' : ''
  }.csv`

  return new NextResponse(body, {
    headers: {
      'content-type': 'text/csv; charset=utf-8',
      'content-disposition': `attachment; filename="${filename}"`,
    },
  })
}
