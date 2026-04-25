// Color map for tag pills on job cards. Keys match function_category, vertical,
// remote_status, and seniority values from db.ts.

export type TagColor = { bg: string; border: string; text: string }

export const TAG_COLORS: Record<string, TagColor> = {
  // function categories
  Marketing:      { bg: 'rgba(139,92,246,0.15)',  border: 'rgba(139,92,246,0.35)',  text: '#A78BFA' },
  Product:        { bg: 'rgba(20,184,166,0.10)',  border: 'rgba(20,184,166,0.30)',  text: '#2DD4BF' },
  Engineering:    { bg: 'rgba(99,102,241,0.10)',  border: 'rgba(99,102,241,0.30)',  text: '#818CF8' },
  Design:         { bg: 'rgba(236,72,153,0.10)',  border: 'rgba(236,72,153,0.30)',  text: '#F472B6' },
  Operations:     { bg: 'rgba(100,116,139,0.15)', border: 'rgba(100,116,139,0.35)', text: '#94A3B8' },
  Sales:          { bg: 'rgba(251,146,60,0.10)',  border: 'rgba(251,146,60,0.30)',  text: '#FB923C' },
  BizDev:         { bg: 'rgba(251,146,60,0.10)',  border: 'rgba(251,146,60,0.30)',  text: '#FB923C' },
  Community:      { bg: 'rgba(236,72,153,0.10)',  border: 'rgba(236,72,153,0.30)',  text: '#F472B6' },
  // verticals
  DeFi:           { bg: 'rgba(0,212,255,0.10)',   border: 'rgba(0,212,255,0.30)',   text: '#67E8F9' },
  L1:             { bg: 'rgba(245,166,35,0.10)',  border: 'rgba(245,166,35,0.30)',  text: '#FCD34D' },
  L2:             { bg: 'rgba(168,85,247,0.10)',  border: 'rgba(168,85,247,0.30)',  text: '#C084FC' },
  Infrastructure: { bg: 'rgba(100,116,139,0.15)', border: 'rgba(100,116,139,0.35)', text: '#94A3B8' },
  Research:       { bg: 'rgba(99,102,241,0.10)',  border: 'rgba(99,102,241,0.30)',  text: '#818CF8' },
  Protocol:       { bg: 'rgba(0,212,255,0.10)',   border: 'rgba(0,212,255,0.30)',   text: '#38BDF8' },
  Oracles:        { bg: 'rgba(245,166,35,0.10)',  border: 'rgba(245,166,35,0.30)',  text: '#FBBF24' },
  Venture:        { bg: 'rgba(139,92,246,0.10)',  border: 'rgba(139,92,246,0.30)',  text: '#A78BFA' },
  Exchange:       { bg: 'rgba(0,212,255,0.10)',   border: 'rgba(0,212,255,0.30)',   text: '#22D3EE' },
  CEX:            { bg: 'rgba(0,212,255,0.10)',   border: 'rgba(0,212,255,0.30)',   text: '#22D3EE' },
  DEX:            { bg: 'rgba(0,212,255,0.10)',   border: 'rgba(0,212,255,0.30)',   text: '#67E8F9' },
  Gaming:         { bg: 'rgba(168,85,247,0.10)',  border: 'rgba(168,85,247,0.30)',  text: '#C084FC' },
  NFT:            { bg: 'rgba(236,72,153,0.10)',  border: 'rgba(236,72,153,0.30)',  text: '#F472B6' },
  RWA:            { bg: 'rgba(20,184,166,0.10)',  border: 'rgba(20,184,166,0.30)',  text: '#2DD4BF' },
  'AI-Crypto':    { bg: 'rgba(99,102,241,0.10)',  border: 'rgba(99,102,241,0.30)',  text: '#818CF8' },
  // remote status
  Remote:         { bg: 'rgba(34,197,94,0.10)',   border: 'rgba(34,197,94,0.30)',   text: '#4ADE80' },
  Hybrid:         { bg: 'rgba(34,197,94,0.10)',   border: 'rgba(34,197,94,0.30)',   text: '#86EFAC' },
  Onsite:         { bg: 'rgba(239,68,68,0.10)',   border: 'rgba(239,68,68,0.30)',   text: '#FCA5A5' },
  // seniority
  Junior:         { bg: 'rgba(34,197,94,0.10)',   border: 'rgba(34,197,94,0.30)',   text: '#4ADE80' },
  Mid:            { bg: 'rgba(100,116,139,0.15)', border: 'rgba(100,116,139,0.35)', text: '#94A3B8' },
  Senior:         { bg: 'rgba(245,166,35,0.10)',  border: 'rgba(245,166,35,0.30)',  text: '#FCD34D' },
  Lead:           { bg: 'rgba(251,146,60,0.10)',  border: 'rgba(251,146,60,0.30)',  text: '#FB923C' },
  Head:           { bg: 'rgba(239,68,68,0.10)',   border: 'rgba(239,68,68,0.30)',   text: '#F87171' },
  Executive:      { bg: 'rgba(168,85,247,0.10)',  border: 'rgba(168,85,247,0.30)',  text: '#C084FC' },
}

export const DEFAULT_TAG: TagColor = {
  bg:     'rgba(160,170,187,0.08)',
  border: 'rgba(160,170,187,0.20)',
  text:   '#A0AABB',
}

export function tagColor(label: string): TagColor {
  return TAG_COLORS[label] ?? DEFAULT_TAG
}
