// Visual % match badge. Colors per plan §6 Phase 5:
//   red <40, yellow 40–59, blue 60–79, green 80+
// null score renders as a muted "Not yet scored" pill.

import { cn } from '@/lib/utils'

export function MatchBadge({ score }: { score: number | null | undefined }) {
  if (score === null || score === undefined) {
    return (
      <span className="inline-flex items-center rounded-md border border-dashed border-muted-foreground/30 px-2 py-0.5 text-xs text-muted-foreground">
        Not yet scored
      </span>
    )
  }
  const tone =
    score >= 80
      ? 'bg-green-500/15 text-green-700 border-green-500/30 dark:text-green-300'
      : score >= 60
      ? 'bg-blue-500/15 text-blue-700 border-blue-500/30 dark:text-blue-300'
      : score >= 40
      ? 'bg-yellow-500/15 text-yellow-700 border-yellow-500/30 dark:text-yellow-300'
      : 'bg-red-500/15 text-red-700 border-red-500/30 dark:text-red-300'
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-semibold tabular-nums',
        tone
      )}
    >
      {score}% match
    </span>
  )
}
