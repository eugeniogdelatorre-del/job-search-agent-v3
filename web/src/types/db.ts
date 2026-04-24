// Hand-written row types for the shapes we actually read in the UI.
// When the schema grows more, regenerate with `supabase gen types` per plan §3.

export type FunctionCategory =
  | 'Community'
  | 'Design'
  | 'Engineering'
  | 'Marketing'
  | 'Operations'
  | 'Sales'
  | 'BizDev'
  | 'Product'
  | 'Other'

export type Seniority =
  | 'Junior'
  | 'Mid'
  | 'Senior'
  | 'Lead'
  | 'Head'
  | 'Executive'
  | 'Unspecified'

export type Vertical =
  | 'DeFi'
  | 'L1'
  | 'L2'
  | 'CEX'
  | 'DEX'
  | 'Gaming'
  | 'Infrastructure'
  | 'NFT'
  | 'RWA'
  | 'Oracles'
  | 'AI-Crypto'
  | 'Other'

export type RemoteStatus = 'Remote' | 'Hybrid' | 'Onsite' | 'Unspecified'

export const FUNCTION_CATEGORIES: FunctionCategory[] = [
  'Community',
  'Design',
  'Engineering',
  'Marketing',
  'Operations',
  'Sales',
  'BizDev',
  'Product',
  'Other',
]

export const SENIORITIES: Seniority[] = [
  'Junior',
  'Mid',
  'Senior',
  'Lead',
  'Head',
  'Executive',
  'Unspecified',
]

export const VERTICALS: Vertical[] = [
  'DeFi',
  'L1',
  'L2',
  'CEX',
  'DEX',
  'Gaming',
  'Infrastructure',
  'NFT',
  'RWA',
  'Oracles',
  'AI-Crypto',
  'Other',
]

export const REMOTE_STATUSES: RemoteStatus[] = [
  'Remote',
  'Hybrid',
  'Onsite',
  'Unspecified',
]

export type Job = {
  id: string
  title: string
  company: string | null
  location: string | null
  remote_status: RemoteStatus | null
  salary_min_usd: number | null
  salary_max_usd: number | null
  salary_source: string | null
  description: string | null
  apply_url: string | null
  source: string
  source_tier: number | null
  source_url: string | null
  function_category: FunctionCategory | null
  function_confidence: number | null
  vertical: Vertical | null
  seniority: Seniority | null
  score_total: number | null
  score_breakdown: Record<string, unknown> | null
  first_seen_at: string
  last_seen_at: string
  is_active: boolean
}

export type JobScore = {
  job_id: string
  resume_id: string
  match_score: number
  strengths: string[]
  gaps: string[]
  verdict_one_liner: string | null
}

export type JobWithScore = Job & {
  job_scores: Pick<JobScore, 'match_score' | 'strengths' | 'gaps' | 'verdict_one_liner'>[]
}
