// Design tokens (Step 9 spec). Single source for colours used in JS.

export const STATUS_COLOUR = {
  SUPPORTED: '#16A34A',
  PARTIALLY_SUPPORTED: '#65A30D',
  INCONCLUSIVE: '#D97706',
  CONTRADICTED: '#DC2626',
  STRONGLY_CONTRADICTED: '#991B1B',
  CONTRADICTED_BY_OWN_EVIDENCE: '#7C3AED',
  GAP: '#6B7280',
}

// status -> {bg tint, text} for badges
export const STATUS_BADGE = {
  SUPPORTED: { bg: '#DCFCE7', text: '#15803D' },
  PARTIALLY_SUPPORTED: { bg: '#ECFCCB', text: '#4D7C0F' },
  INCONCLUSIVE: { bg: '#FEF3C7', text: '#B45309' },
  CONTRADICTED: { bg: '#FEE2E2', text: '#B91C1C' },
  STRONGLY_CONTRADICTED: { bg: '#FEE2E2', text: '#991B1B' },
  CONTRADICTED_BY_OWN_EVIDENCE: { bg: '#F3E8FF', text: '#7C3AED' },
  GAP: { bg: '#F3F4F6', text: '#6B7280' },
}

export const STATUS_LABEL = {
  SUPPORTED: 'Supported',
  PARTIALLY_SUPPORTED: 'Partially supported',
  INCONCLUSIVE: 'Inconclusive',
  CONTRADICTED: 'Contradicted',
  STRONGLY_CONTRADICTED: 'Strongly contradicted',
  CONTRADICTED_BY_OWN_EVIDENCE: 'Contradicted by own evidence',
  GAP: 'Evidence gap',
}

export const DIRECTION_COLOUR = {
  supporting: '#16A34A',
  contradicting: '#DC2626',
  neutral: '#D97706',
}

export const DIRECTION_BADGE = {
  supporting: { bg: '#DCFCE7', text: '#15803D', label: 'Supporting' },
  contradicting: { bg: '#FEE2E2', text: '#B91C1C', label: 'Contradicting' },
  neutral: { bg: '#FEF3C7', text: '#B45309', label: 'Neutral' },
}

export const AUTHOR_BADGE = {
  claimant: { bg: '#DBEAFE', text: '#1E40AF', label: 'Claimant' },
  defendant: { bg: '#FEE2E2', text: '#991B1B', label: 'Defendant' },
  both: { bg: '#F3F4F6', text: '#374151', label: 'Both parties' },
}

export const statusColour = (s) => STATUS_COLOUR[s] || '#6B7280'
