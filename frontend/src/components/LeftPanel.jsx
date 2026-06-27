import { StatusBadge } from './Badges'
import { truncate } from '../lib/labels'

const GAP_STATUSES = new Set(['GAP', 'INCONCLUSIVE'])

export default function LeftPanel({ data, orderedIds, order, setOrder, gapsOnly, setGapsOnly, selectedPropId, onSelect }) {
  const props = data.propositions
  const ss = data.summary_stats

  let ids = orderedIds
  if (gapsOnly) ids = ids.filter((id) => GAP_STATUSES.has(props[id].status))

  const pills = [
    { label: 'Supported', n: ss.supported_count, c: '#16A34A' },
    { label: 'Partial', n: ss.partially_supported_count, c: '#65A30D' },
    { label: 'Contradicted', n: ss.contradicted_count + ss.strongly_contradicted_count, c: '#DC2626' },
    { label: 'Own-evidence', n: ss.contradicted_by_own_evidence_count, c: '#7C3AED' },
    { label: 'Inconclusive', n: ss.inconclusive_count, c: '#D97706' },
    { label: 'Gap', n: ss.gap_count, c: '#6B7280' },
  ]

  return (
    <aside style={{ width: 280, minWidth: 280, borderRight: '1px solid #E5E7EB', background: '#FFFFFF', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* stat pills */}
      <div style={{ padding: 12, borderBottom: '1px solid #E5E7EB', display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {pills.map((p) => (
          <span key={p.label} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, color: '#374151', background: '#F8FAFC', border: '1px solid #E5E7EB', borderRadius: 999, padding: '2px 8px' }}>
            <span style={{ width: 7, height: 7, borderRadius: 999, background: p.c }} />
            {p.label} <b style={{ color: '#111827' }}>{p.n}</b>
          </span>
        ))}
      </div>

      {/* controls */}
      <div style={{ padding: '10px 12px', borderBottom: '1px solid #E5E7EB', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', background: '#F3F4F6', borderRadius: 8, padding: 2 }}>
          {[['risk', 'Risk ranking'], ['allegation', 'Allegation order']].map(([v, label]) => (
            <button
              key={v}
              onClick={() => setOrder(v)}
              style={{
                flex: 1, border: 'none', borderRadius: 6, padding: '5px 8px', fontSize: 12,
                background: order === v ? '#FFFFFF' : 'transparent',
                color: order === v ? '#111827' : '#6B7280',
                fontWeight: order === v ? 600 : 400,
                boxShadow: order === v ? '0 1px 2px rgba(0,0,0,0.06)' : 'none',
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, color: '#374151' }}>
          <input type="checkbox" checked={gapsOnly} onChange={(e) => setGapsOnly(e.target.checked)} />
          Show gaps only
        </label>
      </div>

      {/* allegation list */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {ids.map((id) => {
          const p = props[id]
          const selected = id === selectedPropId
          return (
            <button
              key={id}
              onClick={() => onSelect(id)}
              style={{
                display: 'block', width: '100%', textAlign: 'left', border: 'none',
                background: selected ? '#F0F4FF' : 'transparent',
                borderBottom: '1px solid #F3F4F6',
                borderLeft: selected ? '3px solid #4F46E5' : '3px solid transparent',
                padding: '9px 12px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6, marginBottom: 4 }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: '#111827' }}>Allegation {p.allegation_number}</span>
                <span style={{ fontSize: 11, color: '#6B7280' }}>risk {p.risk_score.toFixed(2)}</span>
              </div>
              <div style={{ marginBottom: 4 }}>
                <StatusBadge status={p.status} dot={p.is_own_evidence_contradiction} />
              </div>
              <div style={{ fontSize: 11, color: '#6B7280', lineHeight: 1.4 }}>{truncate(p.one_line_summary, 90)}</div>
            </button>
          )
        })}
        {ids.length === 0 && (
          <div style={{ padding: 16, fontSize: 12, color: '#9CA3AF' }}>No allegations match this filter.</div>
        )}
      </div>
    </aside>
  )
}
