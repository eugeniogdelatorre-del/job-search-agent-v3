// Colored pill for function category, vertical, seniority, remote status tags.
// Colors come from tagColors.ts — key is the label string.

import { tagColor } from '@/lib/tagColors'

export function TagPill({ label }: { label: string }) {
  const c = tagColor(label)
  return (
    <span
      className="inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[10px] font-medium leading-none"
      style={{ background: c.bg, borderColor: c.border, color: c.text }}
    >
      {label}
    </span>
  )
}
