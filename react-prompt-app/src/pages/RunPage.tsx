/** v2 run page: the app, its spec, and the build activity for a run id. */
import { Link, useParams } from 'react-router-dom'
import { RunStudio } from '../components/RunStudio'

export function RunPage() {
  const { id } = useParams()
  if (!id) return <div className="glass" style={{ padding: 20 }}>No run selected.</div>
  return (
    <div style={{ width: '100%', maxWidth: '100%', margin: '0 auto', padding: '0 0 60px', boxSizing: 'border-box', minWidth: 0 }}>
      <Link to="/constellation" style={{ fontSize: 11.5, color: 'var(--intara-faint)', textDecoration: 'none', display: 'inline-block', marginBottom: 10 }}>← Constellation</Link>
      <RunStudio runId={id} />
    </div>
  )
}
