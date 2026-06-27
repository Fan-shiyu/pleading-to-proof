import { useEffect, useState } from 'react'
import { StatusBadge, AuthorBadge } from './Badges'
import { sourceCredibility, truncate } from '../lib/labels'

export default function DocumentPanel({ data, docId, onClose, onNavigate }) {
  const doc = data.documents.find((d) => d.doc_id === docId)

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // find every proposition this document connects to (via classified chunks)
  const appearances = []
  for (const pid of Object.keys(data.propositions)) {
    const p = data.propositions[pid]
    const chunks = (p.classified_chunks || []).filter((c) => c.doc_id === docId && !c.hallucination_flag)
    if (chunks.length === 0) continue
    // weighted_contribution is read straight from the backend (demo_data.json), not recomputed
    const best = chunks.reduce((a, b) => ((b.weighted_contribution || 0) > (a.weighted_contribution || 0) ? b : a))
    appearances.push({
      pid, p,
      direction: best.final_direction,
      weight: best.weighted_contribution ?? 0,
    })
  }

  if (!doc) return null

  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.12)', zIndex: 40 }} />
      <aside style={{ position: 'fixed', top: 0, right: 0, height: '100vh', width: 320, background: '#FFFFFF', borderLeft: '1px solid #E5E7EB', zIndex: 50, padding: 18, overflow: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
          <h3 style={{ fontSize: 15, fontWeight: 500, margin: 0 }}>{doc.doc_title}</h3>
          <button onClick={onClose} style={{ border: 'none', background: 'none', fontSize: 18, color: '#6B7280', lineHeight: 1 }}>×</button>
        </div>
        <div style={{ fontSize: 13, color: '#6B7280', margin: '4px 0 12px' }}>
          {doc.doc_type}{doc.doc_date ? ` · ${doc.doc_date}` : ''}
        </div>

        <div style={{ fontSize: 12, color: '#374151', marginBottom: 8 }}>{sourceCredibility(doc.source_quality_weight)}</div>
        <div style={{ marginBottom: 16 }}><AuthorBadge party={doc.author_party} /></div>

        <div style={{ fontSize: 12, fontWeight: 600, color: '#374151', textTransform: 'uppercase', letterSpacing: '0.02em', marginBottom: 8 }}>
          Appears in these allegations
        </div>
        {appearances.length === 0 && <div style={{ fontSize: 12, color: '#9CA3AF' }}>Not cited as evidence for any allegation.</div>}
        {appearances.map((a) => (
          <button
            key={a.pid}
            onClick={() => { onNavigate(a.pid); onClose() }}
            style={{ display: 'block', width: '100%', textAlign: 'left', border: '1px solid #E5E7EB', borderRadius: 4, background: '#FFFFFF', padding: 10, marginBottom: 8 }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <span style={{ fontSize: 12, fontWeight: 600 }}>Allegation {a.p.allegation_number}</span>
              <span style={{ fontSize: 11, color: a.direction === 'supporting' ? '#16A34A' : a.direction === 'contradicting' ? '#DC2626' : '#D97706' }}>
                {a.direction} · {a.weight.toFixed(2)}
              </span>
            </div>
            <div style={{ marginBottom: 4 }}><StatusBadge status={a.p.status} /></div>
            <div style={{ fontSize: 11, color: '#6B7280' }}>{truncate(a.p.one_line_summary, 80)}</div>
          </button>
        ))}

        {/* B — all parsed passages from this document, in document order */}
        {doc.passages && doc.passages.length > 0 && (
          <div style={{ marginTop: 18 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#374151', textTransform: 'uppercase', letterSpacing: '0.02em', marginBottom: 8 }}>
              Passages from this document ({doc.passages.length})
            </div>
            <div style={{ fontSize: 10, color: '#9CA3AF', marginBottom: 8 }}>
              Parsed excerpts from the bundle document — not the full original file.
            </div>
            {doc.passages.map((pg) => (
              <PassageRow key={pg.chunk_id} pg={pg} />
            ))}
          </div>
        )}
      </aside>
    </>
  )
}

function PassageRow({ pg }) {
  const [open, setOpen] = useState(false)
  return (
    <div style={{ border: '1px solid #E5E7EB', borderRadius: 4, padding: 9, marginBottom: 6 }}>
      <button onClick={() => setOpen(!open)} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%', border: 'none', background: 'none', padding: 0, textAlign: 'left' }}>
        <span style={{ fontSize: 12, color: '#1E40AF', fontWeight: 500 }}>{pg.citation}</span>
        <span style={{ fontSize: 11, color: '#9CA3AF' }}>{open ? '▲' : '▼'}</span>
      </button>
      {!open && (
        <div style={{ fontSize: 11, color: '#6B7280', marginTop: 4 }}>{truncate(pg.chunk_text, 90)}</div>
      )}
      {open && (
        <div style={{ fontFamily: 'var(--serif)', fontSize: 12, color: '#1F2937', lineHeight: 1.6, marginTop: 6, background: '#F8FAFC', borderRadius: 4, padding: 10 }}>
          {pg.chunk_text}
        </div>
      )}
    </div>
  )
}
