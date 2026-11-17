/** v2 run page: the app, its spec, and the build activity for a run id. */
import { Link, useParams } from 'react-router-dom'
import { RunStudio } from '../components/RunStudio'

export function RunPage() {
  const { id } = useParams()
  if (!id) return <div className="glass" style={{ padding: 20 }}>No run selected.</div>
  return (
    <div style={{ maxWidth: 1240, margin: '0 auto', padding: '20px 16px 60px' }}>
      <Link to="/constellation" style={{ fontSize: 11.5, color: 'var(--intara-faint)', textDecoration: 'none', display: 'inline-block', marginBottom: 10 }}>← Constellation</Link>
      <RunStudio runId={id} />
    </div>
  )
}
