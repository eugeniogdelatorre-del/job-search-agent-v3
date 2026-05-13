import type { JobScore } from '@/types/db'

type Props = {
  score: Pick<JobScore, 'match_score' | 'strengths' | 'gaps' | 'verdict_one_liner' | 'score_breakdown_v5'>
}

// Maxes must mirror scraper/cv_score.py SYSTEM_PREFIX ("DIMENSIONS" table).
// industry_fit dropped 30→20 and title_alignment raised 15→25 in
// 2026-05-07 to weight "is this person actually in the right discipline"
// above "is this person in the exact right vertical." Sum is still 100.
//
// Note: rows already in job_scores were graded against the old scale
// (industry_fit out of 30, title_alignment out of 15). They render as
// "26/20"-style "above max" until cv_score re-scores them — acceptable
// short-term cosmetic. To bulk re-score, run:
//   UPDATE job_scores SET score_breakdown_v5 = NULL;
// and the next cv_score run picks them up.
const DIMENSIONS = [
  { key: 'skill_match',      label: 'Skill Match',   max: 15 },
  { key: 'industry_fit',     label: 'Industry Fit',  max: 20 },
  { key: 'title_alignment',  label: 'Title Align',   max: 25 },
  { key: 'seniority',        label: 'Seniority',     max: 15 },
  { key: 'requirements',     label: 'Requirements',  max: 15 },
  { key: 'geography',        label: 'Geography',     max: 10 },
] as const

type DimensionKey = (typeof DIMENSIONS)[number]['key']

function scoreColor(ratio: number): string {
  if (ratio >= 0.8) return '#4ADE80'
  if (ratio >= 0.5) return '#F5A623'
  return '#FCA5A5'
}

export function ScoreBreakdownPanel({ score }: Props) {
  const dims = score.score_breakdown_v5?.dimensions
  const adjustments = score.score_breakdown_v5?.adjustments ?? []
  const strengths = score.score_breakdown_v5?.strengths ?? score.strengths ?? []
  const gaps = score.score_breakdown_v5?.gaps ?? score.gaps ?? []

  return (
    <div
      className="pt-4 mt-4"
      style={{ borderTop: '1px solid #1E2330' }}
    >
      <p className="font-mono text-[11px] font-semibold uppercase tracking-widest" style={{ color: '#6B7A99' }}>
        Score Breakdown
      </p>

      {/* Dimension bars */}
      {dims && (
        <div className="mt-2 flex flex-col">
          {DIMENSIONS.map(({ key, label, max }) => {
            const dim = dims[key as DimensionKey]
            if (!dim) return null
            const ratio = dim.score / max
            // Audit L23: cap the bar at 100% so an older row that
            // happened to score above the current `max` doesn't overflow
            // its parent. The label still shows the raw score, so the
            // operator can see "scored 22/20" intentionally — only the
            // visual bar width is clamped.
            const barRatio = Math.max(0, Math.min(1, ratio))
            return (
              <div key={key} className="flex items-center gap-2 py-0.5">
                <span className="font-mono text-[10px] w-24 shrink-0" style={{ color: '#6B7A99' }}>
                  {label}
                </span>
                <span
                  className="font-mono text-[10px] w-8 text-right shrink-0"
                  style={{ color: scoreColor(ratio) }}
                >
                  {dim.score}/{max}
                </span>
                <div className="flex-1 h-1 rounded-full" style={{ background: '#1E2330' }}>
                  <div
                    className="h-1 rounded-full bg-[#00D4FF]"
                    style={{ width: `${(barRatio * 100).toFixed(1)}%` }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Adjustments */}
      {adjustments.length > 0 && (
        <div className="mt-3">
          <p className="font-mono text-[11px] font-semibold uppercase tracking-widest" style={{ color: '#6B7A99' }}>
            Adjustments
          </p>
          <div className="flex flex-wrap gap-1.5 mt-1">
            {adjustments.map((adj, i) => {
              const color = adj.value > 0 ? '#4ADE80' : adj.value < 0 ? '#FCA5A5' : '#6B7A99'
              const text = adj.value > 0 ? `+${adj.value} ${adj.label}` : `${adj.value} ${adj.label}`
              return (
                <span key={i} className="font-mono text-[10px]" style={{ color }}>
                  {text}
                </span>
              )
            })}
          </div>
        </div>
      )}

      {/* Verdict */}
      {score.verdict_one_liner && (
        <div className="mt-3">
          <p className="font-mono text-[10px] uppercase tracking-widest" style={{ color: '#3A4460' }}>
            Verdict
          </p>
          <p className="font-body text-[11px] italic leading-relaxed mt-0.5" style={{ color: '#6B7A99' }}>
            {score.verdict_one_liner}
          </p>
        </div>
      )}

      {/* Strengths */}
      {strengths.length > 0 && (
        <div className="mt-3">
          <p className="font-mono text-[10px] uppercase tracking-widest" style={{ color: '#3A4460' }}>
            Strengths
          </p>
          <ul className="mt-1 flex flex-col gap-0.5">
            {strengths.map((s, i) => (
              <li key={i} className="font-body text-[11px] leading-relaxed" style={{ color: '#A0AABB' }}>
                · {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Gaps */}
      {gaps.length > 0 && (
        <div className="mt-3">
          <p className="font-mono text-[10px] uppercase tracking-widest" style={{ color: '#3A4460' }}>
            Gaps
          </p>
          <ul className="mt-1 flex flex-col gap-0.5">
            {gaps.map((g, i) => (
              <li key={i} className="font-body text-[11px] leading-relaxed" style={{ color: '#6B7A99' }}>
                · {g}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
