import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { isSupabaseDemo } from '../supabase'
import { DEMO, GITHUB_URL } from '../demo'

export function Header() {
  const loc = useLocation()
  const nav = useNavigate()
  const { user } = useAuth(!DEMO)
  const isActive = (p: string) => loc.pathname === p || (p !== '/' && loc.pathname.startsWith(p))
  const links = DEMO
    ? [{ to: '/templates', label: 'Live apps' }]
    : [
        { to: '/', label: 'Wish' },
        { to: '/templates', label: 'Templates' },
        { to: '/constellation', label: 'Constellation' },
        { to: '/archives', label: 'Archives' },
      ]
  return (
    <header style={{
      position: 'sticky', top: 0, zIndex: 20,
      backdropFilter: 'blur(24px) saturate(1.2)', WebkitBackdropFilter: 'blur(24px) saturate(1.2)',
      background: 'rgba(7,7,11,0.72)', borderBottom: '1px solid rgba(255,255,255,0.05)',
    }}>
      <div style={{ maxWidth: 1080, margin: '0 auto', padding: '16px 24px', display: 'flex', alignItems: 'center', gap: 20 }}>
        <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: 12, textDecoration: 'none' }}>
          <img src="/assets/planet-intara.png" alt="" width={26} height={26} style={{ borderRadius: '50%', objectFit: 'cover', boxShadow: '0 0 16px rgba(139,92,246,0.32)' }} onError={(e) => (e.currentTarget.style.display = 'none')} />
          <span className="text-display" style={{ fontWeight: 500, letterSpacing: '-0.03em', color: 'var(--intara-text)', fontSize: 15 }}>INTARA</span>
          <span style={{ fontSize: 10, fontWeight: 500, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)', border: '1px solid rgba(255,255,255,0.06)', padding: '3px 8px', borderRadius: 999, background: 'rgba(255,255,255,0.02)' }}>Planet of Wishes</span>
        </Link>
        <nav style={{ display: 'flex', gap: 2, marginLeft: 16 }}>
          {links.map((l) => (
            <Link
              key={l.to}
              to={l.to}
              style={{
                padding: '8px 14px', borderRadius: 999, fontSize: 12.5, fontWeight: isActive(l.to) ? 600 : 450, textDecoration: 'none',
                letterSpacing: '-0.01em',
                color: isActive(l.to) ? 'var(--intara-text)' : 'var(--intara-faint)',
                background: isActive(l.to) ? 'rgba(255,255,255,0.08)' : 'transparent',
                border: `1px solid ${isActive(l.to) ? 'rgba(255,255,255,0.08)' : 'transparent'}`,
                transition: 'all 0.35s var(--ease-premium)',
              }}
            >{l.label}</Link>
          ))}
        </nav>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          {DEMO ? (
            <>
              <span style={{ fontSize: 11, fontWeight: 450, color: 'var(--intara-faint)', border: '1px solid rgba(255,255,255,0.05)', padding: '6px 10px', borderRadius: 999, background: 'rgba(255,255,255,0.02)' }}>Static demo · no backend</span>
              <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="btn-ghost" style={{ fontSize: 12.5, padding: '9px 16px', fontWeight: 500, textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}>GitHub</a>
            </>
          ) : (
            <>
              {isSupabaseDemo ? (
                <span style={{ fontSize: 11, fontWeight: 450, color: 'var(--intara-faint)', border: '1px solid rgba(255,255,255,0.05)', padding: '6px 10px', borderRadius: 999, background: 'rgba(255,255,255,0.02)' }}>Demo · MEM</span>
              ) : user ? (
                <span style={{ fontSize: 11, color: 'var(--intara-muted)', border: '1px solid rgba(255,255,255,0.06)', padding: '6px 10px', borderRadius: 999, background: 'rgba(255,255,255,0.02)' }}>{user.email?.slice(0, 18)}</span>
              ) : null}
              <button onClick={() => nav('/')} className="btn-ghost" style={{ fontSize: 12.5, padding: '9px 16px', fontWeight: 500 }}>New wish ✦</button>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
