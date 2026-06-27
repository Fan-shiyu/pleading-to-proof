import { Bar } from 'react-chartjs-2'
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement, Tooltip, Legend,
} from 'chart.js'
import { StatusBadge } from './Badges'
import { statusColour } from '../lib/tokens'
import { truncate } from '../lib/labels'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend)

export default function Overview({ data, onNavigate }) {
  const ss = data.summary_stats
  const props = data.propositions
  const riskOrder = data.risk_dashboard_order

  const cards = [
    { label: 'Supported', value: ss.supported_count + ss.partially_supported_count, sub: `${ss.supported_count} full · ${ss.partially_supported_count} partial`, c: '#16A34A' },
    { label: 'Contradicted', value: ss.contradicted_count + ss.strongly_contradicted_count + ss.contradicted_by_own_evidence_count, sub: `${ss.contradicted_by_own_evidence_count} by own evidence`, c: '#DC2626' },
    { label: 'Own-evidence contradictions', value: ss.own_evidence_contradiction_count, sub: 'claimant contradicts itself', c: '#7C3AED' },
    { label: 'Inconclusive / gaps', value: ss.inconclusive_count + ss.gap_count, sub: `${ss.gap_count} true gaps`, c: '#D97706' },
  ]

  const top4 = riskOrder.slice(0, 4).map((id) => props[id])

  // risk bar chart for all 17
  const barIds = riskOrder
  const chartData = {
    labels: barIds.map((id) => props[id].allegation_number),
    datasets: [
      {
        label: 'Risk score',
        data: barIds.map((id) => props[id].risk_score),
        backgroundColor: barIds.map((id) => statusColour(props[id].status)),
        borderRadius: 3,
      },
    ],
  }
  const chartOpts = {
    responsive: true, maintainAspectRatio: false,
    onClick: (_e, els) => { if (els.length) onNavigate(barIds[els[0].index]) },
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          title: (items) => `Allegation ${props[barIds[items[0].dataIndex]].allegation_number}`,
          label: (item) => `${props[barIds[item.dataIndex]].status} · risk ${item.raw.toFixed(2)}`,
        },
      },
    },
    scales: { y: { min: 0, max: 1, title: { display: true, text: 'Litigation risk' } } },
  }

  return (
    <div style={{ padding: 20, maxWidth: 1100, margin: '0 auto' }}>
      <h2 style={{ fontSize: 16, fontWeight: 600, margin: '0 0 14px' }}>Case overview</h2>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 20 }}>
        {cards.map((c) => (
          <div key={c.label} style={{ background: '#FFFFFF', border: '1px solid #E5E7EB', borderRadius: 10, padding: 16 }}>
            <div style={{ fontSize: 12, color: '#6B7280' }}>{c.label}</div>
            <div style={{ fontSize: 30, fontWeight: 700, color: c.c, lineHeight: 1.2 }}>{c.value}</div>
            <div style={{ fontSize: 11, color: '#9CA3AF' }}>{c.sub}</div>
          </div>
        ))}
      </div>

      <h3 style={{ fontSize: 14, fontWeight: 600, margin: '0 0 10px' }}>Highest-risk findings</h3>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 22 }}>
        {top4.map((p) => (
          <button
            key={p.proposition_id}
            onClick={() => onNavigate(p.proposition_id)}
            style={{ textAlign: 'left', background: '#FFFFFF', border: '1px solid #E5E7EB', borderLeft: `3px solid ${statusColour(p.status)}`, borderRadius: 10, padding: 14 }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <span style={{ fontSize: 12, fontWeight: 600 }}>Allegation {p.allegation_number}</span>
              <StatusBadge status={p.status} dot={p.is_own_evidence_contradiction} />
            </div>
            <div style={{ fontSize: 12, color: '#374151', lineHeight: 1.5 }}>{truncate(p.one_line_summary, 150)}</div>
            <div style={{ fontSize: 11, color: '#9CA3AF', marginTop: 6 }}>risk {p.risk_score.toFixed(2)}</div>
          </button>
        ))}
      </div>

      <h3 style={{ fontSize: 14, fontWeight: 600, margin: '0 0 10px' }}>Risk by allegation</h3>
      <div style={{ background: '#FFFFFF', border: '1px solid #E5E7EB', borderRadius: 10, padding: 16, height: 280 }}>
        <Bar data={chartData} options={chartOpts} />
      </div>
    </div>
  )
}
