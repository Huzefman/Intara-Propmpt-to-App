import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { isSupabaseDemo } from '../supabase'

export function Header() {
  const loc = useLocation()
  const nav = useNavigate()
  const { user } = useAuth()
  const isActive = (p: string) => loc.pathname === p || (p !== '/' && loc.pathname.startsWith(p))
  return (
    <header style={{
      position: 'sticky', top: 0, zIndex: 20,
      backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)',
      background: 'rgba(10,10,18,0.65)', borderBottom: '1px solid var(--intara-border)',
    }}>
      <div style={{ maxWidth: 1100, margin: '0 auto', padding: '14px 20px', display: 'flex', alignItems: 'center', gap: 18 }}>
        <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none' }}>
          <img src="/assets/planet-intara.png" alt="" width={28} height={28} style={{ borderRadius: '50%', objectFit: 'cover', boxShadow: '0 0 12px rgba(139,92,246,0.5)' }} onError={(e) => (e.currentTarget.style.display = 'none')} />
          <span className="text-display" style={{ fontWeight: 800, letterSpacing: '-.03em', color: 'var(--intara-text)', fontSize: 16 }}>INTARA</span>
          <span style={{ fontSize: 11, color: 'var(--intara-muted)', border: '1px solid var(--intara-border)', padding: '2px 7px', borderRadius: 999 }}>Planet of Wishes</span>
        </Link>
        <nav style={{ display: 'flex', gap: 6, marginLeft: 12 }}>
          {[
            { to: '/', label: 'Wish' },
            { to: '/constellation', label: 'Constellation' },
            { to: '/archives', label: 'Archives' },
          ].map((l) => (
            <Link
              key={l.to}
              to={l.to}
              style={{
                padding: '7px 12px', borderRadius: 999, fontSize: 12, fontWeight: 600, textDecoration: 'none',
                color: isActive(l.to) ? 'var(--intara-bg)' : 'var(--intara-muted)',
                background: isActive(l.to) ? 'var(--intara-text)' : 'transparent',
                border: `1px solid ${isActive(l.to) ? 'var(--intara-text)' : 'transparent'}`,
              }}
            >{l.label}</Link>
          ))}
        </nav>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          {isSupabaseDemo ? (
            <span style={{ fontSize: 11, color: 'var(--intara-faint)', border: '1px solid var(--intara-border)', padding: '5px 9px', borderRadius: 999 }}>Demo • MEM store</span>
          ) : user ? (
            <span style={{ fontSize: 11, color: 'var(--intara-muted)', border: '1px solid var(--intara-border)', padding: '5px 9px', borderRadius: 999 }}>{user.email?.slice(0, 18)}</span>
          ) : null}
          <button onClick={() => nav('/')} className="btn-ghost" style={{ fontSize: 12 }}>New wish ✦</button>
        </div>
      </div>
    </header>
  )
}
