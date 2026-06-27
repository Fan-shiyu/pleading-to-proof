import { useState } from 'react'
import Header from './Header'
import LeftPanel from './LeftPanel'
import Overview from './Overview'
import ProofMatrix from './ProofMatrix'
import RiskDashboard from './RiskDashboard'
import EvidenceGraph from './EvidenceGraph'
import AllegationDetail from './AllegationDetail'
import DocumentPanel from './DocumentPanel'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'proof', label: 'Proof Matrix' },
  { id: 'risk', label: 'Risk Dashboard' },
  { id: 'graph', label: 'Evidence Graph' },
]

export default function MainLayout({ data }) {
  const [activeTab, setActiveTab] = useState('overview')
  const [selectedPropId, setSelectedPropId] = useState(null)
  const [order, setOrder] = useState('risk') // 'risk' | 'allegation'
  const [gapsOnly, setGapsOnly] = useState(false)
  const [docPanelId, setDocPanelId] = useState(null)

  const orderedIds = order === 'risk' ? data.risk_dashboard_order : data.proof_matrix_order

  const navigate = (propId) => {
    setSelectedPropId(propId)
    setDocPanelId(null)
  }
  const clearSelection = () => setSelectedPropId(null)
  const openDoc = (docId) => setDocPanelId(docId)
  const closeDoc = () => setDocPanelId(null)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      <Header caseMeta={data.case_metadata} />
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <LeftPanel
          data={data}
          orderedIds={orderedIds}
          order={order}
          setOrder={setOrder}
          gapsOnly={gapsOnly}
          setGapsOnly={setGapsOnly}
          selectedPropId={selectedPropId}
          onSelect={navigate}
        />
        <main style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {selectedPropId ? (
            <AllegationDetail
              data={data}
              propId={selectedPropId}
              orderedIds={orderedIds}
              order={order}
              onNavigate={navigate}
              onClear={clearSelection}
              onOpenDoc={openDoc}
            />
          ) : (
            <>
              <nav style={{ display: 'flex', gap: 2, padding: '0 16px', borderBottom: '1px solid #E5E7EB', background: '#FFFFFF' }}>
                {TABS.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setActiveTab(t.id)}
                    style={{
                      border: 'none', background: 'none', padding: '12px 14px', fontSize: 13,
                      fontWeight: activeTab === t.id ? 600 : 400,
                      color: activeTab === t.id ? '#111827' : '#6B7280',
                      borderBottom: activeTab === t.id ? '2px solid #4F46E5' : '2px solid transparent',
                    }}
                  >
                    {t.label}
                  </button>
                ))}
              </nav>
              <div style={{ flex: 1, overflow: 'auto', background: activeTab === 'graph' ? '#0F1C3F' : '#F8FAFC' }}>
                {activeTab === 'overview' && <Overview data={data} onNavigate={navigate} />}
                {activeTab === 'proof' && <ProofMatrix data={data} onNavigate={navigate} onOpenDoc={openDoc} />}
                {activeTab === 'risk' && <RiskDashboard data={data} onNavigate={navigate} />}
                {activeTab === 'graph' && <EvidenceGraph data={data} onNavigate={navigate} onOpenDoc={openDoc} />}
              </div>
            </>
          )}
        </main>
      </div>
      {docPanelId && (
        <DocumentPanel data={data} docId={docPanelId} onClose={closeDoc} onNavigate={navigate} />
      )}
    </div>
  )
}
