export default function Header({ caseMeta }) {
  return (
    <header
      style={{
        height: 52, minHeight: 52, display: 'flex', alignItems: 'center',
        padding: '0 16px', borderBottom: '1px solid #E5E7EB', background: '#FFFFFF',
        position: 'sticky', top: 0, zIndex: 30,
      }}
    >
      <div style={{ fontWeight: 700, fontSize: 15, flex: '0 0 auto' }}>
        <span style={{ color: '#00A651' }}>CMS</span>
        <span style={{ color: '#111827' }}> · Pleading to Proof</span>
      </div>
      <div style={{ flex: 1, textAlign: 'center', fontSize: 13, color: '#374151', fontWeight: 500 }}>
        {caseMeta.case_name}
      </div>
      <div style={{ flex: '0 0 auto' }}>
        <span style={{ background: '#00A651', color: '#FFFFFF', fontSize: 11, fontWeight: 600, padding: '3px 10px', borderRadius: 999 }}>
          {caseMeta.claim_number}
        </span>
      </div>
    </header>
  )
}
