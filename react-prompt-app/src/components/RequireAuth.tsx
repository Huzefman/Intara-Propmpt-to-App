import { useLocation, Navigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { DEMO } from '../demo'

/** Account gate for Studio routes. Landing + templates stay public. */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const loc = useLocation()
  const { user, loading } = useAuth(!DEMO)

  if (loading) {
    return (
      <div className="glass" style={{ padding: 40, textAlign: 'center', borderRadius: 20 }}>
        <div style={{ width: 28, height: 28, border: '2px solid rgba(255,255,255,0.06)', borderTopColor: 'var(--intara-nebula)', borderRadius: '50%', animation: 'spin 0.9s var(--ease-fluid) infinite', margin: '0 auto' }} />
        <div style={{ marginTop: 12, fontSize: 12.5, color: 'var(--intara-faint)' }}>Checking your orbit…</div>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/auth" replace state={{ from: loc.pathname + loc.search }} />
  }
  return <>{children}</>
}
