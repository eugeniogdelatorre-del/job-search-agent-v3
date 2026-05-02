# Handoff: job-agent Dark Redesign

## Overview
Complete dark-mode redesign of the `job-agent` personal Web3 job-search dashboard. The aesthetic is Bloomberg terminal meets Dune Analytics meets Linear — data-dense, professional, no neon gimmicks. This covers the `Today` route (main job list) plus stubs for `Apply`, `CV`, `Tune`, and `Settings`.

## About the Design Files
The files in this bundle are **design references created in HTML** — high-fidelity interactive prototypes showing the intended look, feel, and behavior. They are **not** production code to copy directly. Your task is to **recreate these designs inside the existing Next.js 14 / Tailwind v3 / shadcn codebase**, using its established patterns and libraries.

The design was built with React + Babel for rapid prototyping. Map each component to the corresponding Next.js page/component file.

## Fidelity
**High-fidelity.** Colors, typography, spacing, interactions, and microstates are all final. Recreate pixel-perfectly using Tailwind utility classes and CSS variables in `globals.css`. Do not upgrade to Tailwind v4.

---

## Design Tokens

### CSS Variables — add to `globals.css`

```css
:root {
  --bg-base:        #0A0C10;
  --bg-card:        #0F1117;
  --bg-elevated:    #141820;
  --border:         #1E2330;
  --border-mid:     #252D40;
  --accent-cyan:    #00D4FF;
  --accent-cyan-dim:  rgba(0, 212, 255, 0.12);
  --accent-cyan-glow: rgba(0, 212, 255, 0.25);
  --accent-amber:   #F5A623;
  --accent-amber-dim: rgba(245, 166, 35, 0.12);
  --text-primary:   #E8ECF0;
  --text-muted:     #6B7A99;
  --text-mid:       #A0AABB;
  --text-dim:       #3A4460;
}
```

### `tailwind.config.js` — extend colors

```js
extend: {
  colors: {
    base:    '#0A0C10',
    card:    '#0F1117',
    elevated:'#141820',
    border:  { DEFAULT: '#1E2330', mid: '#252D40' },
    cyan:    { DEFAULT: '#00D4FF', dim: 'rgba(0,212,255,0.12)', glow: 'rgba(0,212,255,0.25)' },
    amber:   { DEFAULT: '#F5A623', dim: 'rgba(245,166,35,0.12)' },
    text:    { primary: '#E8ECF0', mid: '#A0AABB', muted: '#6B7A99', dim: '#3A4460' },
  },
  fontFamily: {
    mono:    ['"IBM Plex Mono"', 'monospace'],
    heading: ['Syne', 'sans-serif'],
    body:    ['Inter', 'sans-serif'],
  },
}
```

### Typography

| Role       | Font           | Size  | Weight | Notes                        |
|------------|---------------|-------|--------|------------------------------|
| H1         | Syne           | 36px  | 800    | letter-spacing: -0.04em      |
| Card title | Syne           | 14px  | 700    | letter-spacing: -0.02em      |
| Nav links  | Inter          | 13px  | 500    | letter-spacing: 0.01em       |
| Body small | Inter          | 12px  | 400    | —                            |
| Scores/badges | IBM Plex Mono | 11–18px | 500–600 | All data readouts      |
| Timestamps | IBM Plex Mono  | 10px  | 400    | color: var(--text-dim)       |
| Labels     | IBM Plex Mono  | 9–10px | 500   | uppercase, letter-spacing 0.05–0.08em |

### Font loading — `layout.tsx`
```ts
import { IBM_Plex_Mono, Syne, Inter } from 'next/font/google';

const ibmPlexMono = IBM_Plex_Mono({ subsets: ['latin'], weight: ['400','500','600'], variable: '--font-mono' });
const syne        = Syne({ subsets: ['latin'], weight: ['600','700','800'], variable: '--font-heading' });
const inter       = Inter({ subsets: ['latin'], weight: ['400','500'], variable: '--font-body' });
```

---

## Screens / Views

### 1. Global Layout (`layout.tsx`)

- **Background**: `#0A0C10` with subtle 40×40px grid lines:
  ```css
  background-image:
    linear-gradient(rgba(30,35,48,0.4) 1px, transparent 1px),
    linear-gradient(90deg, rgba(30,35,48,0.4) 1px, transparent 1px);
  background-size: 40px 40px;
  ```
- **Noise overlay**: fixed pseudo-element, `opacity: 0.03`, SVG fractalNoise texture tiled at 128px.
- **Scrollbar**: 6px, track `#0A0C10`, thumb `#252D40`, hover `#6B7A99`.
- `<NavBar>` is sticky at top; page content has `padding-top: 56px`.

---

### 2. NavBar (`components/NavBar.tsx`)

**Structure (flex row, height 56px, full width sticky):**

| Zone    | Content                                            |
|---------|----------------------------------------------------|
| Left    | Hexagon SVG icon (cyan stroke + fill) + "job-agent" wordmark |
| Center  | Navigation links (flex, centered)                  |
| Right   | Email address (muted mono) + "Sign out" ghost button |

**Hex icon SVG:**
```svg
<svg width="18" height="18" viewBox="0 0 18 18">
  <path d="M9 1.5L16 5.25V12.75L9 16.5L2 12.75V5.25L9 1.5Z"
    stroke="#00D4FF" strokeWidth="1.5" fill="rgba(0,212,255,0.08)" strokeLinejoin="round"/>
  <circle cx="9" cy="9" r="2" fill="#00D4FF" opacity="0.7"/>
</svg>
```

**Wordmark:** Syne 16px/700, `#E8ECF0`, letter-spacing -0.02em.

**Nav links:** `["Today","Week","Archive","Apply","CV","Tune","Settings"]`
- Height: 56px, padding: 0 14px
- Inactive: color `#6B7A99`, hover → `#A0AABB`
- Active: color `#E8ECF0` + `border-bottom: 2px solid #00D4FF`
- Transition: `color 0.15s`

**Sign out button:** no background, border `1px solid #252D40`, border-radius 6px, padding `5px 12px`, font 12px/500. Hover: border → `#6B7A99`, color → `#E8ECF0`.

**Bar background:** `rgba(10,12,16,0.95)`, `backdrop-filter: blur(12px)`, border-bottom `1px solid #1E2330`.

---

### 3. Today Page (`app/page.tsx` or `app/today/page.tsx`)

**Page Header**
- H1 "Today" — Syne 36px/800, `#E8ECF0`, letter-spacing -0.04em
- Subtitle — IBM Plex Mono 11px, `#6B7A99`: `{weekday, month day} · {N} positions indexed`
- "export" ghost icon-button (top-right): mono 11px, icon + text, border `#252D40`, border-radius 6px. Same ghost hover pattern.

**Stats Bar** (`components/StatsBar.tsx`)
- 1px-bordered card, background `#0F1117`, border-radius 8px, 5 equal columns separated by vertical `#1E2330` dividers.
- Each cell: value in IBM Plex Mono 18px/600 `#E8ECF0`; label in mono 9px uppercase, `#6B7A99`, margin-top 2px.
- Stats: `indexed | scored | avg match | rule ≥ 70 | saved`

**Filter Bar** (`components/FilterBar.tsx`)
- Background `#0F1117`, border `1px solid #1E2330`, border-radius 10px, padding 14px 16px.
- Flex-wrap row, gap 8px.
- **Search input**: left icon (SVG magnifier, `#6B7A99`), dark fill `rgba(255,255,255,0.03)`, flex-grow.
- **4 Selects**: `Any function`, `Any vertical`, `Any seniority`, `Any location`. Custom chevron SVG in background-image.
- **Divider**: `width:1px, height:24px, background:#1E2330`.
- **Numeric inputs** (IBM Plex Mono): `min $` (width 80px), `rule ≥` (width 64px), `match ≥` (width 64px).
- **Focus/active state**: `border-color: #00D4FF; box-shadow: 0 0 0 2px rgba(0,212,255,0.15)`.
- **Clear button**: appears when any filter active. Mono 10px, ghost style.

---

### 4. Job Card (`components/JobCard.tsx`)

**Layout** — flex column, gap 10px, padding 16px. Background `#0F1117`, border `1px solid #1E2330`, border-radius 10px.

**Default → Hover transition:**
- Border: `#1E2330` → `rgba(0,212,255,0.35)` (`transition: border-color 0.18s`)
- Box-shadow: none → `0 0 0 1px rgba(0,212,255,0.1), 0 4px 24px rgba(0,212,255,0.06)`
- Transform: none → `translateY(-1px)` (`transition: transform 0.18s`)
- Top accent line: absolute positioned, `height:1px`, `background: linear-gradient(90deg, transparent, rgba(0,212,255,0.5), transparent)` on hover, else transparent.

**Row 1 — Title + Match Badge**
- Title: Syne 14px/700, `#E8ECF0`, `-webkit-line-clamp: 2`, flex-1
- Match badge (`<MatchBadge>`):
  - `null` → dim pill `color:#3A4460 bg:#141820 border:#1E2330`, italic mono 11px, text "—"
  - `≥ 85%` → `color:#00D4FF bg:rgba(0,212,255,0.12) border:rgba(0,212,255,0.4)`, mono 11px/600
  - `70–84%` → `color:#67E8F9 bg:rgba(103,232,249,0.08) border:rgba(103,232,249,0.3)`
  - `< 70%` → `color:#A0AABB bg:rgba(160,170,187,0.08) border:rgba(160,170,187,0.2)`
  - All badges: padding `2px 8px`, border-radius 20px

**Row 2 — Company · Location**
- Company: Inter 12px/500, `#A0AABB`
- Separator dot: `#252D40`
- Location: Inter 12px, `#6B7A99`

**Row 3 — Tag Pills + Rule Badge**
- Tag pills (`<TagPill>`): 10px/500, border-radius 20px, padding `2px 8px`. Colors per category (see Tag Color Map below).
- Rule badge (`<RuleBadge>`): IBM Plex Mono 10px/500, border-radius 4px, padding `2px 7px`, text format `rule: {N}`.
  - `≥ 70`: `color:#F5A623 bg:rgba(245,166,35,0.10) border:rgba(245,166,35,0.3)`
  - `50–69`: `color:#A0AABB bg:rgba(160,170,187,0.07) border:rgba(160,170,187,0.2)`
  - `< 50`: `color:#3A4460 bg:transparent border:#1E2330`

**Row 4 — Salary** (optional, togglable via settings)
- IBM Plex Mono 10px, `#3A4460`

**Row 5 — Bottom Bar**
- Left: IBM Plex Mono 10px, `#3A4460`: `{posted} · via {source}`
- Right: Bookmark icon + Apply button
- **Bookmark** (`<BookmarkButton>`): SVG, 14×14. Unfilled = `#6B7A99`; saved = amber fill `#F5A623`. Toggle on click.
- **Apply button**: Solid `#00D4FF` bg, black text, mono 10px/600, border-radius 5px, padding `5px 12px`, text `"apply →"`. On hover: `transform: scale(1.03)`. Applied state: `bg:rgba(0,212,255,0.15) border:rgba(0,212,255,0.4) color:#00D4FF text:"applied ✓"`.

---

### Tag Color Map

```ts
export const TAG_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  Marketing:      { bg: 'rgba(139,92,246,0.15)',  border: 'rgba(139,92,246,0.35)',  text: '#A78BFA' },
  DeFi:           { bg: 'rgba(0,212,255,0.10)',   border: 'rgba(0,212,255,0.30)',   text: '#67E8F9' },
  Remote:         { bg: 'rgba(34,197,94,0.10)',   border: 'rgba(34,197,94,0.30)',   text: '#4ADE80' },
  Growth:         { bg: 'rgba(251,146,60,0.10)',  border: 'rgba(251,146,60,0.30)',  text: '#FB923C' },
  Protocol:       { bg: 'rgba(0,212,255,0.10)',   border: 'rgba(0,212,255,0.30)',   text: '#38BDF8' },
  L1:             { bg: 'rgba(245,166,35,0.10)',  border: 'rgba(245,166,35,0.30)',  text: '#FCD34D' },
  L2:             { bg: 'rgba(168,85,247,0.10)',  border: 'rgba(168,85,247,0.30)',  text: '#C084FC' },
  Research:       { bg: 'rgba(99,102,241,0.10)',  border: 'rgba(99,102,241,0.30)',  text: '#818CF8' },
  Product:        { bg: 'rgba(20,184,166,0.10)',  border: 'rgba(20,184,166,0.30)',  text: '#2DD4BF' },
  BD:             { bg: 'rgba(239,68,68,0.10)',   border: 'rgba(239,68,68,0.30)',   text: '#F87171' },
  Infrastructure: { bg: 'rgba(100,116,139,0.15)', border: 'rgba(100,116,139,0.35)', text: '#94A3B8' },
  Community:      { bg: 'rgba(236,72,153,0.10)',  border: 'rgba(236,72,153,0.30)',  text: '#F472B6' },
  Oracle:         { bg: 'rgba(245,166,35,0.10)',  border: 'rgba(245,166,35,0.30)',  text: '#FBBF24' },
  Venture:        { bg: 'rgba(139,92,246,0.10)',  border: 'rgba(139,92,246,0.30)',  text: '#A78BFA' },
  Operations:     { bg: 'rgba(100,116,139,0.15)', border: 'rgba(100,116,139,0.35)', text: '#94A3B8' },
  Exchange:       { bg: 'rgba(0,212,255,0.10)',   border: 'rgba(0,212,255,0.30)',   text: '#22D3EE' },
  Hybrid:         { bg: 'rgba(34,197,94,0.10)',   border: 'rgba(34,197,94,0.30)',   text: '#86EFAC' },
  Onsite:         { bg: 'rgba(239,68,68,0.10)',   border: 'rgba(239,68,68,0.30)',   text: '#FCA5A5' },
};
```

---

### 5. Loading & Empty States

**Skeleton card** — same dimensions as a job card. Three shimmer blocks:
- Title row: `height:16px width:65%`
- Company row: `height:13px width:45%`
- Tags row: 3 pills `height:20px width:72/56/64px border-radius:20px`
- Bottom: `height:11px width:30%` + `height:26px width:68px`

**Shimmer animation** (`globals.css`):
```css
@keyframes shimmer {
  0%   { background-position: -200% 0; }
  100% { background-position:  200% 0; }
}
.skeleton {
  background: linear-gradient(90deg, #1E2330 25%, #252D40 50%, #1E2330 75%);
  background-size: 200% 100%;
  animation: shimmer 1.8s infinite;
  border-radius: 4px;
}
```

**Empty state** — centered SVG icon (dim) + two lines of mono text:
- Line 1: `"no jobs match your filters"` — mono 13px, `#6B7A99`
- Line 2: `"try relaxing your criteria"` — mono 11px, `#3A4460`

---

### 6. /apply — Kanban Board

- 5 columns: `Saved | Applied | Interview | Offer | Rejected`
- Column grid: `grid-template-columns: repeat(5, 1fr)`, gap 12px.
- Column card: `#0F1117`, border `#1E2330`, border-radius 10px, padding 12px.
- Column header: dot (7px circle, column color) + label (mono 11px/600 uppercase, `#A0AABB`) + count (mono 10px, `#3A4460`). Separated by `border-bottom: 1px solid #1E2330`.
- Column colors: Saved `#6B7A99` · Applied `#00D4FF` · Interview `#A78BFA` · Offer `#4ADE80` · Rejected `#F87171`
- Kanban card: same anatomy as job card but **no Apply button**. Background `#0A0C10`. Hover: same cyan border lift.

---

### 7. /settings — Settings Page

**MTD Spend chart**: SVG area chart. Cyan stroke `#00D4FF` 1.5px. Area fill: `linearGradient` from `rgba(0,212,255,0.2)` → `rgba(0,212,255,0)`. Contained in a `#0F1117` card with mono label.

**Source Health table**: `#0F1117` card, `border-radius:10px overflow:hidden`. Columns: Source · Status · Jobs today · Latency.
- Status dot: 6px circle. `healthy=#4ADE80 degraded=#F5A623 down=#F87171`.
- Rows separated by `border-bottom: 1px solid #1E2330`.
- Header row cells: mono 10px uppercase, `#3A4460`.

---

### 8. /tune — JSON Config Editor

- macOS-style traffic-light dots header row (red/amber/green, 8px circles) + `agent.config.json` mono label.
- `<textarea>` filling the card. Background: transparent (card is `#0F1117`). Font: IBM Plex Mono 12px, color `#67E8F9`, line-height 1.7. Resize: vertical.
- "save config →" button: solid cyan, black text, mono 12px/600, border-radius 7px, padding `10px 24px`. Saved state: `rgba(0,212,255,0.15)` background, cyan text, "saved ✓".

---

### 9. /resume — CV Upload

- Upload zone: `border: 2px dashed #252D40`, border-radius 12px, padding 40px, centered. Drag-over state: border → `#00D4FF`, background `rgba(0,212,255,0.04)`.
- CV list: flex column, gap 8px. Each row: `#0F1117` card, border `#1E2330`, padding `12px 16px`. File icon + filename (mono 11px) + size/date (mono 10px, `#3A4460`) + "activate" ghost button or "active" cyan badge.

---

## Interactions & Animations

| Element           | Trigger     | Behavior                                                      |
|-------------------|-------------|---------------------------------------------------------------|
| Nav link          | click       | Set active page, update `border-bottom` + color              |
| Job card          | hover       | Border cyan glow, `translateY(-1px)`, top shimmer line       |
| Apply button      | click       | Toggle applied state, persist to DB/state                     |
| Bookmark          | click       | Toggle saved state, icon fills amber                          |
| Filter inputs     | change      | Real-time filter of job list (client-side or server action)  |
| Clear button      | click       | Reset all filters to defaults                                 |
| Skeleton shimmer  | loading     | CSS animation, 1.8s infinite                                  |
| Save config       | click       | POST config, button shows "saved ✓" for 2s                   |
| CV drag-over      | dragover    | Dashed border cyan, subtle bg tint                            |

## State Management

Use React `useState` for filter state. Suggest lifting job list fetching to a Server Component; pass down as props. Filter client-side with `Array.filter()` unless job count exceeds ~500, then use URL search params + server filtering.

```ts
// Filter shape
interface Filters {
  search: string;
  func: string;       // "Any function" | specific function
  vertical: string;
  seniority: string;
  location: string;
  minSalary: string;
  minRule: string;
  minMatch: string;
}
```

---

## Files in This Bundle

| File                  | Description                                   |
|-----------------------|-----------------------------------------------|
| `job-agent.html`      | Full interactive prototype — primary reference |
| `README.md`           | This document                                  |

## Prompt for Claude Code

Paste this into your Claude Code session:

```
Here is the redesigned component from Claude Design. Integrate this into my Next.js 14 / Tailwind v3 / shadcn project. The existing routes are /, /week, /archive, /apply, /resume, /tune, /settings.

1. Apply the dark theme globally via globals.css CSS variables (see README Design Tokens section).
2. Extend tailwind.config.js with the custom colors and font families from the README.
3. Load IBM Plex Mono, Syne, and Inter via next/font/google in layout.tsx.
4. Implement the NavBar as a sticky client component.
5. Implement JobCard, MatchBadge, RuleBadge, TagPill, FilterBar, StatsBar as client components.
6. The job list grid uses CSS grid with 3 columns (responsive: 1 col mobile, 2 col tablet, 3 col desktop).
7. Add the shimmer skeleton CSS to globals.css.
8. Do NOT upgrade to Tailwind v4.

Reference job-agent.html for all visual details. Reference README.md for exact measurements, colors, and interactions.
```
