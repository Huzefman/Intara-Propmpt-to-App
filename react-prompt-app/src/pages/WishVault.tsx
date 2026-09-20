import { useParams, Link } from 'react-router-dom'
import { useWish } from '../hooks/useWish'
import { ArtifactVault } from '../components/ArtifactVault'

export function WishVault() {
  const { id } = useParams()
  const { wish, loading, err } = useWish(id)

  if (loading && !wish) return <div className="glass" style={{ padding: 24, textAlign: 'center', color: 'var(--intara-muted)' }}>Intara is weaving your wish… ✨</div>
  if (err) return <div className="glass" style={{ padding: 20, color: '#f87171' }}>{err} <Link to="/" style={{ color: '#8B5CF6' }}>Make another wish</Link></div>
  if (!wish) return <div className="glass" style={{ padding: 20, color: 'var(--intara-muted)' }}>Wish not found.</div>

  if (wish.status === 'weaving') {
    return (
      <div className="glass" style={{ padding: 28, textAlign: 'center' }}>
        <div style={{ fontFamily: 'Space Grotesk', fontSize: 18, fontWeight: 700 }}>Weaving stardust…</div>
        <div style={{ color: 'var(--intara-muted)', fontSize: 13, marginTop: 6 }}>Intara is forging schemas, frontend, backend, and scroll. This takes ~8s.</div>
        <div style={{ marginTop: 14, width: 36, height: 36, border: '3px solid rgba(255,255,255,0.12)', borderTopColor: '#8B5CF6', borderRadius: '50%', animation: 'spin 1s linear infinite', marginInline: 'auto' }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
      </div>
    )
  }

  if (wish.status === 'failed') {
    return <div className="glass" style={{ padding: 20, color: '#f87171' }}>Intara failed to weave. Try again. <Link to="/" style={{ color: '#8B5CF6' }}>New wish</Link></div>
  }

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <Link to="/" style={{ fontSize: 12, color: 'var(--intara-muted)', textDecoration: 'none' }}>← New wish</Link>
          <div style={{ fontFamily: 'Space Grotesk', fontSize: 22, fontWeight: 800, marginTop: 4 }}>{wish.prd?.appName || 'Wish granted'} <span style={{ fontWeight: 400, color: 'var(--intara-muted)', fontSize: 13 }}>• {new Date(wish.created_at).toLocaleString()}</span></div>
          <div style={{ color: 'var(--intara-muted)', fontSize: 12, marginTop: 4, maxWidth: 720 }}>{wish.prompt}</div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'start' }}>
          <Link to="/constellation" className="btn-ghost" style={{ textDecoration: 'none', display: 'inline-block', padding: '9px 14px' }}>View constellation</Link>
        </div>
      </div>
      <ArtifactVault wish={wish} />
    </div>
  )
}
