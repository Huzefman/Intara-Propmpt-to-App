import { Header } from './Header'
import { useLocation } from 'react-router-dom'

export function Layout({ children }: { children: React.ReactNode }) {
  const loc = useLocation()
  const studio = loc.pathname.startsWith('/wish/')
  if (studio) {
    // Builder page: true edge-to-edge, no global header/footer (Rocket-style)
    return (
      <div className="intara-shell">
        <main style={{ padding: 0, margin: 0, maxWidth: 'none' }}>
          {children}
        </main>
      </div>
    )
  }
  const isRun = loc.pathname.startsWith('/runs/')
  return (
    <div className="intara-shell">
      <Header />
      <main style={{ maxWidth: isRun ? 1520 : 1240, margin: '0 auto', padding: isRun ? '24px 20px 80px' : '40px 24px 80px' }}>
        {children}
      </main>
      <footer style={{
        textAlign: 'center',
        padding: '36px 24px 44px',
        fontSize: 13,
        fontWeight: 400,
        letterSpacing: '0.01em',
        color: 'var(--intara-dim)',
        borderTop: '1px solid rgba(255,255,255,0.04)',
        marginTop: 36,
      }}>
        <span style={{ color: 'var(--intara-faint)' }}>Crafted with Intara</span>
        <span style={{ margin: '0 12px', opacity: 0.3 }}>·</span>
        <span>Turn any idea into a live working app</span>
        <span style={{ margin: '0 12px', opacity: 0.3 }}>·</span>
        <span>Private &amp; Secure</span>
      </footer>
    </div>
  )
}
