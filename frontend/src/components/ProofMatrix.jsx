import { StatusBadge } from './Badges'
import { statusColour } from '../lib/tokens'
import { proofLabel, truncate } from '../lib/labels'

export default function ProofMatrix({ data, onNavigate, onOpenDoc }) {
  const props = data.propositions
  const ids = data.proof_matrix_order

  const miniBar = (frac, colour) => (
    <div style={{ width: 70, height: 5, background: '#E5E7EB', borderRadius: 3, overflow: 'hidden', display: 'inline-block', verticalAlign: 'middle' }}>
      <div style={{ width: `${Math.max(0, Math.min(1, frac)) * 100}%`, height: '100%', background: colour }} />
    </div>
  )

  return (
    <div style={{ padding: 20 }}>
      <h2 style={{ fontSize: 16, fontWeight: 600, margin: '0 0 14px' }}>Proof matrix</h2>
      <div style={{ background: '#FFFFFF', border: '1px solid #E5E7EB', borderRadius: 10, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ background: '#F8FAFC', color: '#6B7280', textAlign: 'left' }}>
              <th style={th}>§</th>
              <th style={th}>Allegation</th>
              <th style={th}>Status</th>
              <th style={th}>Proof</th>
              <th style={th}>Risk</th>
              <th style={th}>Evidence</th>
              <th style={th}>Top citation</th>
              <th style={th}>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {ids.map((id) => {
              const p = props[id]
              const md = p.most_determinative_citation
              return (
                <tr
                  key={id}
                  onClick={() => onNavigate(id)}
                  style={{ borderTop: '1px solid #F3F4F6', borderLeft: `3px solid ${statusColour(p.status)}`, cursor: 'pointer' }}
                >
                  <td style={td}>{p.allegation_number}</td>
                  <td style={{ ...td, maxWidth: 280 }}>{truncate(p.proposition_text, 60)}</td>
                  <td style={td}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                      {p.is_own_evidence_contradiction && <span style={{ width: 6, height: 6, borderRadius: 999, background: '#7C3AED' }} />}
                      <StatusBadge status={p.status} />
                    </span>
                  </td>
                  <td style={td}>
                    {miniBar(Math.abs(p.proof_score || 0), statusColour(p.status))}{' '}
                    <span style={{ color: '#6B7280', marginLeft: 4 }}>{proofLabel(p.proof_score)}</span>
                  </td>
                  <td style={td}>
                    {miniBar(p.risk_score, '#DC2626')} <span style={{ marginLeft: 4 }}>{p.risk_score.toFixed(2)}</span>
                  </td>
                  <td style={td}>
                    <span style={{ color: '#16A34A' }}>{p.supporting_count} for</span> ·{' '}
                    <span style={{ color: '#DC2626' }}>{p.contradicting_count} against</span>
                  </td>
                  <td style={td}>
                    {md ? (
                      <span
                        onClick={(e) => { e.stopPropagation(); onOpenDoc(md.doc_id || idToDoc(md, p)) }}
                        style={{ color: '#1D4ED8', textDecoration: 'none', cursor: 'pointer' }}
                        onMouseEnter={(e) => (e.currentTarget.style.textDecoration = 'underline')}
                        onMouseLeave={(e) => (e.currentTarget.style.textDecoration = 'none')}
                      >
                        {md.citation}
                      </span>
                    ) : (
                      <span style={{ color: '#9CA3AF' }}>—</span>
                    )}
                  </td>
                  <td style={{ ...td, color: '#6B7280' }}>{p.classification_confidence}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// most_determinative_citation has no doc_id; resolve from the matching classified chunk
function idToDoc(md, p) {
  const ch = (p.classified_chunks || []).find((c) => c.citation === md.citation)
  return ch ? ch.doc_id : null
}

const th = { padding: '9px 12px', fontWeight: 500, whiteSpace: 'nowrap' }
const td = { padding: '9px 12px', verticalAlign: 'middle' }
