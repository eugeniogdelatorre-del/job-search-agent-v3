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

export type ScoreBreakdownDimension = {
  score: number
  notes: string
}

export type ScoreBreakdownV5 = {
  location_eligible?: boolean
  subtotal?: number
  dimensions?: {
    skill_match: ScoreBreakdownDimension
    industry_fit: ScoreBreakdownDimension
    title_alignment: ScoreBreakdownDimension
    seniority: ScoreBreakdownDimension
    requirements: ScoreBreakdownDimension
    geography: ScoreBreakdownDimension
  }
  adjustments?: { label: string; value: number }[]
  strengths?: string[]
  gaps?: string[]
}

export type JobScore = {
  job_id: string
  resume_id: string
  match_score: number
  strengths: string[]
  gaps: string[]
  verdict_one_liner: string | null
  score_breakdown_v5: ScoreBreakdownV5 | null
}

export type JobWithScore = Job & {
  job_scores: Pick<JobScore, 'match_score' | 'strengths' | 'gaps' | 'verdict_one_liner' | 'score_breakdown_v5'>[]
}

export type ApplicationStatus =
  | 'saved'
  | 'applied'
  | 'interview'
  | 'offer'
  | 'rejected'

export const APPLICATION_STATUSES: ApplicationStatus[] = [
  'saved',
  'applied',
  'interview',
  'offer',
  'rejected',
]

export type Application = {
  id: string
  user_id: string
  job_id: string | null
  job_title_snapshot: string
  company_snapshot: string | null
  apply_url_snapshot: string | null
  source_snapshot: string | null
  status: ApplicationStatus
  applied_at: string | null
  notes: string | null
  created_at: string
  updated_at: string
}
