import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { isSupabaseDemo } from '../supabase'
import { DEMO, GITHUB_URL } from '../demo'

export function Header() {
  const loc = useLocation()
  const nav = useNavigate()
  const { user, signOut } = useAuth(!DEMO)
  const onAuth = loc.pathname === '/auth'
  const isActive = (p: string) => loc.pathname === p || (p !== '/' && loc.pathname.startsWith(p))
  const links = DEMO
    ? [{ to: '/templates', label: 'Live apps' }]
    : user
      ? [
          { to: '/', label: 'Wish' },
          { to: '/templates', label: 'Templates' },
          { to: '/constellation', label: 'Constellation' },
          { to: '/archives', label: 'Archives' },
          { to: '/account', label: 'Account' },
        ]
      : [
          { to: '/', label: 'Wish' },
          { to: '/templates', label: 'Templates' },
        ]

  const userInitial = (user?.email?.[0] || 'U').toUpperCase()
  const username = user?.email ? user.email.split('@')[0] : 'Account'

  return (
    <header className="site-header">
      <div className="header-container">
        <div className="header-brand-wrap">
          <Link to="/" className="header-brand">
            <img
              src="/assets/planet-intara.png"
              alt=""
              width={26}
              height={26}
              className="header-brand-logo"
              onError={(e) => (e.currentTarget.style.display = 'none')}
            />
            <span className="text-display header-brand-title">INTARA</span>
            <span className="header-tagline">Planet of Wishes</span>
          </Link>
        </div>

        <nav className="header-nav" aria-label="Main Navigation">
          {links.map((l) => (
            <Link
              key={l.to}
              to={l.to}
              className={`header-nav-link ${isActive(l.to) ? 'active' : ''}`}
            >
              {l.label}
            </Link>
          ))}
        </nav>

        <div className="header-actions">
          {DEMO ? (
            <>
              <span className="header-badge">Static demo · no backend</span>
              <a
                href={GITHUB_URL}
                target="_blank"
                rel="noreferrer"
                className="btn-ghost btn-sm"
                style={{ fontSize: 12, padding: '5px 13px', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', height: 32 }}
              >
                GitHub
              </a>
            </>
          ) : isSupabaseDemo ? (
            <span className="header-badge">Demo · MEM</span>
          ) : onAuth ? null : user ? (
            <>
              <button
                onClick={() => nav('/')}
                className="header-new-wish-btn"
                title="Create a new app with a wish"
              >
                <span className="header-wish-star">✦</span>
                <span className="header-wish-text">New wish</span>
              </button>

              <div className="header-user-capsule">
                <Link
                  to="/account"
                  className="header-user-profile"
                  title={`Signed in as ${user.email} · Account & Keys`}
                >
                  <span className="header-user-avatar">{userInitial}</span>
                  <span className="header-user-name">{username}</span>
                </Link>
                <span className="header-user-divider" aria-hidden="true" />
                <button
                  onClick={async () => { await signOut(); nav('/') }}
                  className="header-signout-btn"
                  title="Sign out of your account"
                  aria-label="Sign out"
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                    <polyline points="16 17 21 12 16 7" />
                    <line x1="21" y1="12" x2="9" y2="12" />
                  </svg>
                  <span className="header-signout-label">Sign out</span>
                </button>
              </div>
            </>
          ) : (
            <>
              <button
                onClick={() => nav('/auth')}
                className="btn-ghost btn-sm"
                style={{ fontSize: 12, padding: '6px 14px', height: 32 }}
              >
                Sign in
              </button>
              <button
                onClick={() => nav('/auth?mode=signup')}
                className="btn-primary btn-sm"
                style={{ fontSize: 12, padding: '6px 14px', height: 32 }}
              >
                Create account
              </button>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
