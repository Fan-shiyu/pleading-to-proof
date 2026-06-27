import { useState } from 'react'
import { StatusBadge } from './Badges'
import { statusColour, DIRECTION_COLOUR, DIRECTION_BADGE } from '../lib/tokens'
import { proofLabel, sourceCredibility } from '../lib/labels'

const wc = (c) =>
  c.weighted_contribution != null
    ? c.weighted_contribution
    : Math.abs(c.score || 0) * (c.source_quality_weight || 0) * (c.confidence || 0)

const dirRank = { contradicting: 0, supporting: 1, neutral: 2 }

export default function AllegationDetail({ data, propId, orderedIds, order, onNavigate, onClear, onOpenDoc }) {
  const p = data.propositions[propId]
  const idx = orderedIds.indexOf(propId)

  const chunks = (p.classified_chunks || [])
    .filter((c) => !c.hallucination_flag)
    .sort((a, b) => {
      const dr = (dirRank[a.final_direction] ?? 3) - (dirRank[b.final_direction] ?? 3)
      return dr !== 0 ? dr : wc(b) - wc(a)
    })

  const isGap = p.retrieval_gap && (p.classified_chunks || []).length === 0

  return (
    <div style={{ overflow: 'auto', padding: 20, maxWidth: 880, margin: '0 auto', width: '100%' }}>
      <button onClick={onClear} style={{ border: 'none', background: 'none', color: '#4F46E5', fontSize: 13, padding: 0, marginBottom: 14 }}>
        ← All allegations
      </button>

      {/* header */}
      <div style={{ background: '#FFFFFF', border: '1px solid #E5E7EB', borderRadius: 10, padding: 18, marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
          <h2 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>Allegation {p.allegation_number}</h2>
          <StatusBadge status={p.status} dot={p.is_own_evidence_contradiction} />
          <span style={{ fontSize: 12, color: '#9CA3AF' }}>{p.classification_confidence} confidence</span>
        </div>
        <p style={{ fontSize: 15, color: '#1F2937', lineHeight: 1.55, margin: '0 0 14px' }}>{p.proposition_text}</p>

        <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap', marginBottom: 10 }}>
          <div>
            <div style={{ fontSize: 11, color: '#6B7280', marginBottom: 4 }}>Proof score · {proofLabel(p.proof_score)}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ width: 140, height: 6, background: '#E5E7EB', borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ width: `${Math.abs(p.proof_score || 0) * 100}%`, height: '100%', background: statusColour(p.status) }} />
              </div>
              <span style={{ fontSize: 12, color: '#374151' }}>{p.proof_score == null ? '—' : p.proof_score.toFixed(2)}</span>
            </div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: '#6B7280', marginBottom: 4 }}>Litigation risk</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ width: 140, height: 6, background: '#E5E7EB', borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ width: `${p.risk_score * 100}%`, height: '100%', background: 'linear-gradient(90deg,#16A34A,#D97706,#DC2626)' }} />
              </div>
              <span style={{ fontSize: 12, color: '#374151' }}>{p.risk_score.toFixed(2)}</span>
            </div>
          </div>
        </div>
        <div style={{ fontSize: 13, color: '#6B7280', fontStyle: 'italic' }}>{p.one_line_summary}</div>
      </div>

      {/* own-evidence banner */}
      {p.is_own_evidence_contradiction && (
        <div style={{ background: '#FAF5FF', borderLeft: '3px solid #7C3AED', borderRadius: 6, padding: '12px 16px', marginBottom: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 500, color: '#6D28D9', marginBottom: 6 }}>
            ⚠ This allegation is contradicted by the claimant's own evidence
          </div>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {(p.own_evidence_citations || []).map((e, i) => (
              <li key={i} style={{ fontSize: 12, color: '#7C3AED', marginBottom: 2 }}>
                {e.citation} — {e.doc_title}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* gap state */}
      {isGap && (
        <div style={{ textAlign: 'center', padding: 40, color: '#6B7280' }}>
          <div style={{ fontSize: 34 }}>○</div>
          <div style={{ fontSize: 15, fontWeight: 600, margin: '8px 0' }}>No evidence retrieved</div>
          <div style={{ fontSize: 13 }}>{p.no_evidence_note || 'No evidence has been identified in this bundle for this allegation.'}</div>
        </div>
      )}

      {/* evidence cards */}
      {chunks.map((c) => (
        <EvidenceCard key={c.chunk_id} c={c} onOpenDoc={onOpenDoc} />
      ))}

      {/* human review */}
      {p.human_review_count > 0 && (
        <div style={{ background: '#FFFBEB', border: '1px solid #FCD34D', borderRadius: 8, padding: '12px 16px', marginTop: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#92400E', marginBottom: 6 }}>
            Requires human review — {p.human_review_count} chunk(s)
          </div>
          {(p.human_review_citations || []).map((h, i) => (
            <div key={i} style={{ fontSize: 12, color: '#92400E' }}>
              {h.citation} — {h.note}
            </div>
          ))}
        </div>
      )}

      {/* prev / next */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 22, paddingTop: 14, borderTop: '1px solid #E5E7EB' }}>
        <button disabled={idx <= 0} onClick={() => onNavigate(orderedIds[idx - 1])} style={navBtn(idx <= 0)}>← Previous</button>
        <span style={{ fontSize: 12, color: '#6B7280' }}>
          {idx + 1} of {orderedIds.length} · sorted by {order === 'risk' ? 'risk' : 'allegation'}
        </span>
        <button disabled={idx >= orderedIds.length - 1} onClick={() => onNavigate(orderedIds[idx + 1])} style={navBtn(idx >= orderedIds.length - 1)}>Next →</button>
      </div>
    </div>
  )
}

function EvidenceCard({ c, onOpenDoc }) {
  const [expanded, setExpanded] = useState(false)
  const colour = DIRECTION_COLOUR[c.final_direction] || '#D97706'
  const badge = DIRECTION_BADGE[c.final_direction] || DIRECTION_BADGE.neutral
  return (
    <div style={{ background: '#FFFFFF', border: '1px solid #E5E7EB', borderLeft: `3px solid ${colour}`, borderRadius: 10, padding: 14, marginBottom: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ background: badge.bg, color: badge.text, fontSize: 11, fontWeight: 500, padding: '2px 8px', borderRadius: 999 }}>{badge.label}</span>
        <span onClick={() => onOpenDoc(c.doc_id)} style={{ fontSize: 13, color: '#1E40AF', cursor: 'pointer', fontWeight: 500 }}>{c.citation}</span>
        {c.metadata_rule_applied && (
          <span style={{ background: '#F3F4F6', color: '#6B7280', fontSize: 10, padding: '2px 6px', borderRadius: 999 }}>Rule-based</span>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 11, color: '#9CA3AF' }}>{sourceCredibility(c.source_quality_weight)}</span>
      </div>
      <div style={{ fontSize: 11, color: '#6B7280', marginBottom: 8 }}>
        <span style={{ color: '#374151', fontWeight: 500 }}>{c.doc_title}</span>
        {c.doc_type ? ` · ${c.doc_type}` : ''}{c.doc_date ? ` · ${c.doc_date}` : ''}
      </div>
      <blockquote style={{ margin: '0 0 8px', borderLeft: '2px solid #E5E7EB', paddingLeft: 14, fontFamily: 'var(--serif)', fontSize: 13, color: '#1F2937', lineHeight: 1.6 }}>
        <span style={{ color: '#9CA3AF' }}>“</span>{c.verbatim_quote}<span style={{ color: '#9CA3AF' }}>”</span>
      </blockquote>
      <div style={{ fontSize: 12, color: '#6B7280' }}>{c.reason}</div>
      <button onClick={() => setExpanded(!expanded)} style={{ border: 'none', background: 'none', color: '#4F46E5', fontSize: 12, padding: '6px 0 0' }}>
        {expanded ? 'Show less ↑' : 'Read full passage ↓'}
      </button>
      {expanded && (
        <div style={{ background: '#F8FAFC', borderRadius: 6, padding: 12, marginTop: 8, fontSize: 12, color: '#374151', lineHeight: 1.55 }}>
          {c.chunk_text}
        </div>
      )}
    </div>
  )
}

const navBtn = (disabled) => ({
  border: '1px solid #E5E7EB', background: disabled ? '#F8FAFC' : '#FFFFFF',
  color: disabled ? '#D1D5DB' : '#374151', borderRadius: 8, padding: '6px 12px', fontSize: 12,
  cursor: disabled ? 'default' : 'pointer',
})
