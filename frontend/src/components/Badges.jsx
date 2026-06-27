import { STATUS_BADGE, STATUS_LABEL, AUTHOR_BADGE, DIRECTION_BADGE } from '../lib/tokens'

// DESIGN.md: status badges are rectangular (2px radius), with a 1px border
// of a darker shade from the same hue. No pills.
const badgeStyle = (b) => ({
  display: 'inline-flex', alignItems: 'center', gap: 5,
  background: b.bg, color: b.text, fontSize: 11, fontWeight: 500,
  padding: '2px 7px', borderRadius: 2, border: `1px solid ${b.text}33`,
  whiteSpace: 'nowrap', letterSpacing: '0.01em',
})

export function StatusBadge({ status, dot }) {
  const b = STATUS_BADGE[status] || STATUS_BADGE.GAP
  return (
    <span style={badgeStyle(b)}>
      {dot && <span style={{ width: 6, height: 6, borderRadius: 1, background: '#7C3AED', display: 'inline-block' }} />}
      {STATUS_LABEL[status] || status}
    </span>
  )
}

export function DirectionBadge({ direction }) {
  const b = DIRECTION_BADGE[direction] || DIRECTION_BADGE.neutral
  return <span style={badgeStyle(b)}>{b.label}</span>
}

export function AuthorBadge({ party }) {
  const b = AUTHOR_BADGE[party] || AUTHOR_BADGE.both
  return <span style={badgeStyle(b)}>{b.label}</span>
}

// centred proof bar (negative = left/red, positive = right/green) — simple coloured bar
export function ProofBar({ score, status, width = 140 }) {
  const colour = status ? `var(--status-${statusVar(status)})` : '#6B7280'
  const pct = score === null || score === undefined ? 0 : Math.abs(score) * 100
  return (
    <div style={{ width, height: 6, background: '#E5E7EB', borderRadius: 3, overflow: 'hidden' }}>
      <div style={{ width: `${pct}%`, height: '100%', background: STATUS_HEX(status) }} />
    </div>
  )
}

export function RiskBar({ score, width = 140 }) {
  // green -> red gradient, filled to score
  return (
    <div style={{ width, height: 6, background: '#E5E7EB', borderRadius: 3, overflow: 'hidden' }}>
      <div style={{ width: `${(score || 0) * 100}%`, height: '100%', background: 'linear-gradient(90deg,#16A34A,#D97706,#DC2626)' }} />
    </div>
  )
}

function statusVar(s) {
  return {
    SUPPORTED: 'supported', PARTIALLY_SUPPORTED: 'partially', INCONCLUSIVE: 'inconclusive',
    CONTRADICTED: 'contradicted', STRONGLY_CONTRADICTED: 'strongly',
    CONTRADICTED_BY_OWN_EVIDENCE: 'own', GAP: 'gap',
  }[s] || 'gap'
}

function STATUS_HEX(s) {
  return {
    SUPPORTED: '#16A34A', PARTIALLY_SUPPORTED: '#65A30D', INCONCLUSIVE: '#D97706',
    CONTRADICTED: '#DC2626', STRONGLY_CONTRADICTED: '#991B1B',
    CONTRADICTED_BY_OWN_EVIDENCE: '#7C3AED', GAP: '#6B7280',
  }[s] || '#6B7280'
}
