import { Header } from './Header'

export function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="intara-shell">
      <Header />
      <main style={{ maxWidth: 1100, margin: '0 auto', padding: '28px 20px 60px' }}>
        {children}
      </main>
      <footer style={{ textAlign: 'center', padding: '0 20px 28px', fontSize: 11, color: 'var(--intara-faint)' }}>
        Intara listens from 3.7 light years away • Built on Gemini • Supabase • Vite • <span style={{ color: 'var(--intara-muted)' }}>planet of wishes</span>
      </footer>
    </div>
  )
}
