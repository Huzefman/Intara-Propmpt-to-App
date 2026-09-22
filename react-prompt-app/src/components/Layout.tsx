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
  return (
    <div className="intara-shell">
      <Header />
      <main style={{ maxWidth: 1080, margin: '0 auto', padding: '40px 24px 80px' }}>
        {children}
      </main>
      <footer style={{
        textAlign: 'center',
        padding: '32px 24px 40px',
        fontSize: 11,
        fontWeight: 400,
        letterSpacing: '0.02em',
        color: 'var(--intara-dim)',
        borderTop: '1px solid rgba(255,255,255,0.04)',
        marginTop: 32,
      }}>
        <span style={{ color: 'var(--intara-faint)' }}>Intara listens from 3.7 light years away</span>
        <span style={{ margin: '0 12px', opacity: 0.3 }}>·</span>
        <span>Gemini</span>
        <span style={{ margin: '0 8px', opacity: 0.3 }}>·</span>
        <span>Supabase</span>
        <span style={{ margin: '0 8px', opacity: 0.3 }}>·</span>
        <span>Vite</span>
      </footer>
    </div>
  )
}
