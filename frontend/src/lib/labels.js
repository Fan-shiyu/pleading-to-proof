// Plain-English label helpers (Step 9 spec).

export function proofLabel(score) {
  if (score === null || score === undefined) return 'No evidence'
  if (score >= 0.6) return 'Clearly established'
  if (score >= 0.2) return 'Partially established'
  if (score >= -0.2) return 'Not clearly established'
  if (score >= -0.6) return 'Contradicted'
  return 'Strongly contradicted'
}

export function sourceCredibility(weight) {
  const w = Number(weight)
  if (w === 1.0) return 'Primary record — highest credibility'
  if (w === 0.95) return 'Independent expert opinion'
  if (w === 0.9) return 'Contemporaneous correspondence'
  if (w === 0.8) return 'Witness evidence'
  if (w === 0.75) return 'Legal correspondence'
  return 'Source weight ' + w
}

export function riskWording(score) {
  if (score >= 0.75) return 'Critical'
  if (score >= 0.5) return 'High'
  if (score >= 0.3) return 'Moderate'
  return 'Low'
}

export const truncate = (s, n) => (s && s.length > n ? s.slice(0, n).trimEnd() + '…' : s || '')

// proof_score in [-1,1] -> width fraction [0,1] for a centred bar
export const proofBarPct = (s) => (s === null || s === undefined ? 0 : Math.abs(s) * 100)
