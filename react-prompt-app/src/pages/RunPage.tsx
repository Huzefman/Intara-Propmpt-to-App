/** v2 run view: Blueprint (cards, approve, chat, versions, preview) for a run id. */
import { useParams } from 'react-router-dom'
import { BlueprintView } from '../components/BlueprintView'

export function RunPage() {
  const { id } = useParams()
  if (!id) return <div className="glass" style={{ padding: 20 }}>No run selected.</div>
  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '20px 16px 60px', display: 'grid', gap: 12 }}>
      <BlueprintView runId={id} />
    </div>
  )
}
