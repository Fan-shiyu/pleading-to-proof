import { Bubble } from 'react-chartjs-2'
import { Chart as ChartJS, LinearScale, PointElement, Tooltip, Legend } from 'chart.js'
import { StatusBadge } from './Badges'
import { statusColour, STATUS_COLOUR, STATUS_LABEL } from '../lib/tokens'
import { truncate } from '../lib/labels'

ChartJS.register(LinearScale, PointElement, Tooltip, Legend)

function hexToRgba(hex, a) {
  const m = hex.replace('#', '')
  const r = parseInt(m.slice(0, 2), 16), g = parseInt(m.slice(2, 4), 16), b = parseInt(m.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${a})`
}

// Draws the four quadrant labels inside the plot area corners (uses chartArea,
// so they never collide with the axis ticks/titles).
const quadrantLabels = {
  id: 'quadrantLabels',
  afterDraw(chart) {
    const { ctx, chartArea } = chart
    if (!chartArea) return
    const { left, right, top, bottom } = chartArea
    const pad = 8
    ctx.save()
    ctx.font = '11px Inter, sans-serif'
    ctx.fillStyle = '#9CA3AF'
    // Top labels sit ABOVE the grid (in the top padding band) so they never
    // overlap the high-importance bubbles clustered at the top of the plot.
    ctx.textBaseline = 'bottom'
    ctx.textAlign = 'left'
    ctx.fillText('High importance · Low risk', left + pad, top - 7)
    ctx.textAlign = 'right'
    ctx.fillText('High importance · High risk', right - pad, top - 7)
    // Bottom labels stay inside the plot — the low-importance region has no bubbles.
    ctx.textAlign = 'left'
    ctx.fillText('Low importance · Low risk', left + pad, bottom - pad)
    ctx.textAlign = 'right'
    ctx.fillText('Low importance · High risk', right - pad, bottom - pad)
    ctx.restore()
  },
}

const STATUS_ORDER = [
  'SUPPORTED', 'PARTIALLY_SUPPORTED', 'INCONCLUSIVE',
  'CONTRADICTED', 'STRONGLY_CONTRADICTED', 'CONTRADICTED_BY_OWN_EVIDENCE', 'GAP',
]

export default function RiskDashboard({ data, onNavigate }) {
  const props = data.propositions
  const ids = Object.keys(props)

  const points = ids.map((id) => {
    const p = props[id]
    return { x: p.risk_score, y: p.importance_weight, r: Math.abs(p.proof_score || 0) * 20 + 8, _id: id }
  })

  const chartData = {
    datasets: [
      {
        label: 'Allegations',
        data: points,
        backgroundColor: ids.map((id) => hexToRgba(statusColour(props[id].status), 0.8)),
        borderColor: ids.map((id) => statusColour(props[id].status)),
        borderWidth: 1,
        clip: false, // allow full bubbles to render past the plot edge
      },
    ],
  }

  const opts = {
    responsive: true, maintainAspectRatio: false,
    layout: { padding: { top: 26, right: 18, bottom: 4, left: 4 } },
    onClick: (_e, els) => { if (els.length) onNavigate(points[els[0].index]._id) },
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          title: (items) => `Allegation ${props[points[items[0].dataIndex]._id].allegation_number}`,
          label: (item) => {
            const p = props[points[item.dataIndex]._id]
            return [`${p.status} · risk ${p.risk_score.toFixed(2)}`, truncate(p.one_line_summary, 70),
              p.most_determinative_citation ? p.most_determinative_citation.citation : '']
          },
        },
      },
    },
    scales: {
      // extend max slightly past 1 so bubbles centred at 1.0 are not clipped
      x: { min: 0, max: 1.08, ticks: { stepSize: 0.1 }, title: { display: true, text: 'Litigation risk →' } },
      y: { min: 0, max: 1.08, ticks: { stepSize: 0.1 }, title: { display: true, text: 'Allegation importance ↑' } },
    },
  }

  const statusesPresent = STATUS_ORDER.filter((s) => ids.some((id) => props[id].status === s))
  const top5 = data.risk_dashboard_order.slice(0, 5).map((id) => props[id])

  return (
    <div style={{ padding: '24px 20px 28px', maxWidth: 1000, margin: '0 auto' }}>
      <h2 style={{ fontSize: 16, fontWeight: 600, margin: '0 0 14px' }}>Risk dashboard</h2>

      <div style={{ background: '#FFFFFF', border: '1px solid #E5E7EB', borderRadius: 4, padding: 16, height: 440 }}>
        <Bubble data={chartData} options={opts} plugins={[quadrantLabels]} />
      </div>

      {/* legend: colour = status, size = strength of proof */}
      <div style={{ background: '#FFFFFF', border: '1px solid #E5E7EB', borderRadius: 4, padding: '10px 14px', marginTop: 10 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 12, fontSize: 12, color: '#374151' }}>
          <span style={{ fontWeight: 600 }}>Colour = status:</span>
          {statusesPresent.map((s) => (
            <span key={s} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: STATUS_COLOUR[s], display: 'inline-block' }} />
              {STATUS_LABEL[s]}
            </span>
          ))}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 12, color: '#374151', marginTop: 10 }}>
          <span style={{ fontWeight: 600 }}>Bubble size = strength of proof:</span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 12, height: 12, borderRadius: '50%', background: '#9CA3AF', display: 'inline-block' }} /> weak
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 24, height: 24, borderRadius: '50%', background: '#9CA3AF', display: 'inline-block' }} /> strong
          </span>
          <span style={{ color: '#9CA3AF' }}>(magnitude of the proof score, whether supporting or contradicting)</span>
        </div>
      </div>

      <h3 style={{ fontSize: 14, fontWeight: 600, margin: '20px 0 10px' }}>Top 5 highest-risk allegations</h3>
      <div style={{ background: '#FFFFFF', border: '1px solid #E5E7EB', borderRadius: 4, overflow: 'hidden' }}>
        {top5.map((p) => (
          <button
            key={p.proposition_id}
            onClick={() => onNavigate(p.proposition_id)}
            style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', textAlign: 'left', border: 'none', background: 'none', borderTop: '1px solid #F3F4F6', borderLeft: `3px solid ${statusColour(p.status)}`, padding: '10px 12px' }}
          >
            <span style={{ fontSize: 12, fontWeight: 600, width: 90 }}>Alleg. {p.allegation_number}</span>
            <StatusBadge status={p.status} dot={p.is_own_evidence_contradiction} />
            <span style={{ fontSize: 12, color: '#6B7280', flex: 1 }}>{truncate(p.one_line_summary, 90)}</span>
            <span style={{ fontSize: 12, fontWeight: 600, color: '#DC2626' }}>{p.risk_score.toFixed(2)}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
