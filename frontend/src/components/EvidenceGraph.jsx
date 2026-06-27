import { useEffect, useRef, useState, useMemo } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { statusColour } from '../lib/tokens'
import { truncate } from '../lib/labels'

const EDGE_COLOUR = { SUPPORTS: '#16A34A', CONTRADICTS: '#DC2626', CITES: '#3B82F6' }

export default function EvidenceGraph({ data, onNavigate, onOpenDoc }) {
  const [graph, setGraph] = useState(null)
  const [mode, setMode] = useState('document_view')
  const [minSim, setMinSim] = useState(0.3)
  const [docPanel, setDocPanel] = useState(null)
  const wrapRef = useRef(null)
  const fgRef = useRef(null)
  const [size, setSize] = useState({ w: 800, h: 560 })

  useEffect(() => {
    fetch('graph_data.json').then((r) => r.json()).then(setGraph).catch(() => {})
  }, [])

  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [graph])

  const gdata = useMemo(() => {
    if (!graph) return { nodes: [], links: [] }
    const view = graph[mode]
    const nodes = view.nodes.map((n) => ({ ...n }))
    const links = view.edges
      .filter((e) => e.edge_type !== 'CORROBORATES' || (e.similarity ?? 1) >= minSim)
      .map((e) => ({ ...e, source: e.source, target: e.target }))
    return { nodes, links }
  }, [graph, mode, minSim])

  const propStatus = (id) => data.propositions[id]?.status

  const drawNode = (node, ctx, scale) => {
    const label = node.label ?? node.id
    if (node.node_type === 'proposition') {
      const s = 9
      const colour = statusColour(propStatus(node.id))
      ctx.save()
      ctx.translate(node.x, node.y)
      ctx.rotate(Math.PI / 4)
      ctx.fillStyle = colour
      ctx.fillRect(-s, -s, s * 2, s * 2)
      ctx.restore()
    } else {
      ctx.beginPath()
      ctx.arc(node.x, node.y, 8, 0, 2 * Math.PI)
      ctx.fillStyle = node.colour || '#9CA3AF'
      ctx.fill()
    }
    if (scale > 1.2 || node.node_type === 'proposition') {
      ctx.font = `${11 / scale}px Inter, sans-serif`
      ctx.fillStyle = '#E5E7EB'
      ctx.textAlign = 'center'
      ctx.fillText(String(label), node.x, node.y + 16)
    }
  }

  const onNodeClick = (node) => {
    if (node.node_type === 'proposition') onNavigate(node.id)
    else setDocPanel(node.id)
  }

  if (!graph) return <div style={{ padding: 30, color: '#9CA3AF' }}>Loading graph…</div>

  return (
    <div ref={wrapRef} style={{ position: 'relative', width: '100%', height: '100%', minHeight: 560, background: '#0F1C3F' }}>
      <ForceGraph2D
        ref={fgRef}
        width={size.w}
        height={size.h}
        graphData={gdata}
        backgroundColor="#0F1C3F"
        nodeCanvasObject={drawNode}
        nodePointerAreaPaint={(node, colour, ctx) => {
          ctx.fillStyle = colour
          ctx.beginPath(); ctx.arc(node.x, node.y, 10, 0, 2 * Math.PI); ctx.fill()
        }}
        nodeLabel={(n) =>
          n.node_type === 'proposition'
            ? `Allegation ${data.propositions[n.id]?.allegation_number} · ${propStatus(n.id)} · risk ${data.propositions[n.id]?.risk_score?.toFixed(2)}`
            : `${n.label} · ${n.doc_type} · edges ${n.edge_count ?? 0}`
        }
        linkColor={(l) => EDGE_COLOUR[l.edge_type] || '#64748B'}
        linkWidth={(l) => (l.edge_type === 'CITES' ? 1 : Math.max(1, (l.total_weight || 1) * 1.2))}
        linkLineDash={(l) => (l.edge_type === 'CITES' ? [4, 3] : null)}
        linkDirectionalParticles={0}
        onNodeClick={onNodeClick}
        onBackgroundClick={() => setDocPanel(null)}
        cooldownTicks={120}
      />

      {/* controls overlay */}
      <div style={{ position: 'absolute', top: 12, right: 12, background: '#FFFFFF', borderRadius: 10, padding: 12, width: 210, fontSize: 12 }}>
        <div style={{ display: 'flex', background: '#F3F4F6', borderRadius: 6, padding: 2, marginBottom: 10 }}>
          {[['document_view', 'Document'], ['detailed_view', 'Detailed']].map(([m, l]) => (
            <button key={m} onClick={() => setMode(m)} style={{ flex: 1, border: 'none', borderRadius: 4, padding: '4px 6px', fontSize: 11, background: mode === m ? '#FFFFFF' : 'transparent', color: mode === m ? '#111827' : '#6B7280', fontWeight: mode === m ? 600 : 400 }}>{l} view</button>
          ))}
        </div>
        <label style={{ display: 'block', color: '#6B7280', marginBottom: 4 }}>Connection strength: {minSim.toFixed(2)}</label>
        <input type="range" min="0.3" max="1" step="0.05" value={minSim} onChange={(e) => setMinSim(parseFloat(e.target.value))} style={{ width: '100%' }} />
        <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 4, color: '#374151' }}>
          <Legend colour="#16A34A" label="Supports" />
          <Legend colour="#DC2626" label="Contradicts" />
          <Legend colour="#3B82F6" label="Cites" dashed />
        </div>
      </div>

      {docPanel && <GraphDocPanel data={data} docId={docPanel} onClose={() => setDocPanel(null)} onNavigate={onNavigate} />}
    </div>
  )
}

function Legend({ colour, label, dashed }) {
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{ width: 16, height: 0, borderTop: `2px ${dashed ? 'dashed' : 'solid'} ${colour}` }} />
      {label}
    </span>
  )
}

// in-graph side panel of connected propositions, grouped by direction
function GraphDocPanel({ data, docId, onClose, onNavigate }) {
  const groups = { supporting: [], contradicting: [], neutral: [] }
  for (const pid of Object.keys(data.propositions)) {
    const p = data.propositions[pid]
    for (const c of p.classified_chunks || []) {
      if (c.doc_id === docId && !c.hallucination_flag && c.final_direction) {
        ;(groups[c.final_direction] || groups.neutral).push({ pid, p, c })
        break
      }
    }
  }
  const doc = data.documents.find((d) => d.doc_id === docId)
  return (
    <aside style={{ position: 'absolute', top: 0, right: 0, height: '100%', width: 300, background: '#FFFFFF', borderLeft: '1px solid #E5E7EB', padding: 16, overflow: 'auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, margin: 0 }}>{doc?.doc_title || docId}</h3>
        <button onClick={onClose} style={{ border: 'none', background: 'none', fontSize: 18, color: '#6B7280' }}>×</button>
      </div>
      {['contradicting', 'supporting', 'neutral'].map((dir) =>
        groups[dir].length ? (
          <div key={dir} style={{ marginTop: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', color: dir === 'supporting' ? '#16A34A' : dir === 'contradicting' ? '#DC2626' : '#D97706', marginBottom: 6 }}>{dir}</div>
            {groups[dir].map(({ pid, p }) => (
              <button key={pid} onClick={() => onNavigate(pid)} style={{ display: 'block', width: '100%', textAlign: 'left', border: '1px solid #E5E7EB', borderRadius: 4, background: '#FFFFFF', padding: 8, marginBottom: 6, fontSize: 12 }}>
                <b>Allegation {p.allegation_number}</b> — {truncate(p.one_line_summary, 70)}
              </button>
            ))}
          </div>
        ) : null
      )}
    </aside>
  )
}
