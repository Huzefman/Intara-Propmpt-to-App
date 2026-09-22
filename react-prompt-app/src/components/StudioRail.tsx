import { Link, useLocation, useNavigate } from 'react-router-dom'

function Icon({ d }: { d: string }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  )
}

export function StudioRail({ collapsed = false, onToggle }: { collapsed?: boolean; onToggle?: () => void }) {
  const loc = useLocation()
  const nav = useNavigate()
  const items = [
    { to: '/', label: 'Home', d: 'M3 10.5 12 3l9 7.5M5 9.5V21h5v-6h4v6h5V9.5' },
    { to: '/constellation', label: 'Constellation', d: 'M12 3v3m0 12v3M3 12h3m12 0h3M6.3 6.3l2 2m7.4 7.4 2 2m0-11.4-2 2M8.3 15.7l-2 2' },
    { to: '/archives', label: 'Archives', d: 'M4 4h16v5H4zM6 9v11h12V9M10 13h4' },
  ]
  return (
    <nav className={`studio-rail glass ${collapsed ? 'collapsed' : ''}`} aria-label="Studio navigation">
      <button className="studio-rail-logo" onClick={() => nav('/')} aria-label="Intara home" title="Intara home">✦</button>
      {items.map((it) => (
        <Link key={it.to} to={it.to} title={it.label} aria-label={it.label} className={`studio-rail-btn ${loc.pathname === it.to ? 'active' : ''}`}>
          <Icon d={it.d} />
          {!collapsed && <span className="studio-rail-label">{it.label}</span>}
        </Link>
      ))}
      <div style={{ flex: 1 }} />
      <button className="studio-rail-btn studio-rail-new" onClick={() => nav('/')} title="New wish" aria-label="New wish">
        <span aria-hidden="true" style={{ fontSize: 18, lineHeight: 1 }}>+</span>
        {!collapsed && <span className="studio-rail-label">New wish</span>}
      </button>
      {onToggle && (
        <button className="studio-rail-toggle" onClick={onToggle} title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} aria-expanded={!collapsed}>
          {collapsed ? '›' : '‹'}
        </button>
      )}
    </nav>
  )
}
