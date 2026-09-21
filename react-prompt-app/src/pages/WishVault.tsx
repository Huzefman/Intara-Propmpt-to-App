import { useParams, Link } from 'react-router-dom'
import { useCallback } from 'react'
import { useWish } from '../hooks/useWish'
import { AgentThread } from '../components/AgentThread'
import { StudioPreview } from '../components/StudioPreview'
import { StudioRail } from '../components/StudioRail'
import { ArtifactVault } from '../components/ArtifactVault'
import { streamBuild } from '../api/client'
import { getWish } from '../api/client'
import { useEffect, useState } from 'react'

export function WishVault() {
  const { id } = useParams()
  const { wish, loading, err, setWish } = useWish(id)
  const refresh = useCallback(async () => {
    if (!id) return
    try { setWish(await getWish(id)) } catch { /* keep current */ }
  }, [id, setWish])

  if (loading && !wish) return <div className="glass" style={{ padding: 40, textAlign: 'center', borderRadius: 20 }}>
    <div style={{ width: 32, height: 32, border: '2px solid rgba(255,255,255,0.06)', borderTopColor: 'var(--intara-nebula)', borderRadius: '50%', animation: 'spin 0.9s var(--ease-fluid) infinite', margin: '0 auto' }} />
    <div style={{ fontFamily: 'Space Grotesk', fontSize: 14, fontWeight: 500, letterSpacing: '-0.02em', marginTop: 16, color: 'var(--intara-text)' }}>Opening studio…</div>
    <div style={{ color: 'var(--intara-faint)', fontSize: 12.5, marginTop: 6, fontWeight: 400 }}>Intara is listening</div>
    <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
  </div>
  if (err) return <div className="glass" style={{ padding: 20, color: '#FCA5A5', borderRadius: 16 }}>{err} <Link to="/" style={{ color: 'var(--intara-nebula-light)' }}>Make another wish</Link></div>
  if (!wish) return <div className="glass" style={{ padding: 24, textAlign: 'center', color: 'var(--intara-faint)', borderRadius: 16 }}>Wish not found.</div>

  const building = wish.status === 'building' || wish.status === 'approved'
  // Legacy one-shot wishes keep the classic vault view
  if (wish.status === 'weaving' || (wish.status === 'ready' && !wish.prd?.buildGraph)) {
    if (wish.status === 'weaving') {
      return (
        <div className="glass" style={{ padding: 40, textAlign: 'center', borderRadius: 20 }}>
          <div style={{ width: 36, height: 36, border: '2.5px solid rgba(255,255,255,0.06)', borderTopColor: 'var(--intara-nebula)', borderRadius: '50%', animation: 'spin 0.9s var(--ease-fluid) infinite', margin: '0 auto' }} />
          <div style={{ fontFamily: 'Space Grotesk', fontSize: 15, fontWeight: 500, letterSpacing: '-0.02em', marginTop: 16 }}>Weaving stardust…</div>
          <div style={{ color: 'var(--intara-faint)', fontSize: 12.5, marginTop: 6, fontWeight: 400, letterSpacing: '-0.01em' }}>Forging schemas · frontend · backend · scroll</div>
          <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
        </div>
      )
    }
    return (
      <div>
        <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', alignItems: 'flex-start' }}>
          <div>
            <Link to="/" style={{ fontSize: 11.5, fontWeight: 450, letterSpacing: '0.01em', color: 'var(--intara-faint)', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 6 }}>← New wish</Link>
            <div style={{ fontFamily: 'Space Grotesk', fontSize: 26, fontWeight: 400, letterSpacing: '-0.03em', marginTop: 8, color: 'var(--intara-text)' }}>
              {wish.prd?.appName || 'Wish granted'}
              <span style={{ fontWeight: 300, color: 'var(--intara-faint)', fontSize: 13, marginLeft: 10, letterSpacing: '-0.01em' }}>{new Date(wish.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</span>
            </div>
            <div style={{ color: 'var(--intara-faint)', fontSize: 12.5, fontWeight: 400, marginTop: 6, maxWidth: 640, lineHeight: 1.6, letterSpacing: '-0.01em' }}>{wish.prompt}</div>
          </div>
        </div>
        <ArtifactVault wish={wish} />
      </div>
    )
  }

  // Staged Studio: rail + agent thread + live preview
  return (
    <div className="studio-grid">
      <StudioRail />
      <div className="studio-thread-col">
        <div className="studio-thread-head">
          <strong>{wish.prd?.appName && wish.status !== 'planning' ? wish.prd.appName : 'New wish'}</strong>
          <span className={`pill status-${wish.status}`}>{wish.status.replace('_', ' ')}</span>
        </div>
        <AgentThread wish={wish} onChanged={refresh} buildView={building ? <BuildingView wish={wish} compact /> : undefined} />
      </div>
      <StudioPreview wish={wish} />
    </div>
  )
}

function BuildingView({ wish, compact = false }: { wish: any; compact?: boolean }) {
  const [steps, setSteps] = useState<any>(wish.artifacts?.steps || {})
  const [log, setLog] = useState<any[]>([])

  useEffect(() => {
    // SSE
    const close = streamBuild(wish.id, (ev:any) => {
      if (ev.event === 'step_started' || ev.event === 'step_done' || ev.event === 'step_failed') {
        setSteps((prev:any) => ({ ...prev, [ev.data.stepId]: { status: ev.event === 'step_started' ? 'running' : ev.event === 'step_done' ? 'done' : 'failed', ...ev.data }}))
      }
      setLog(prev => [...prev.slice(-20), ev])
      if (ev.event === 'build_done' || ev.event === 'build_failed') {
        // will be updated via polling as well, but force reload after 1s
        setTimeout(() => window.location.reload(), 800)
      }
    })
    // polling fallback every 2s
    const iv = setInterval(async () => {
      try {
        const res = await fetch(`/api/wish/${wish.id}`)
        if (res.ok) {
          const data = await res.json()
          if (data.artifacts?.steps) setSteps(data.artifacts.steps)
          if (data.status === 'ready' || data.status === 'failed') {
            clearInterval(iv)
            setTimeout(() => window.location.reload(), 500)
          }
        }
      } catch {}
    }, 2000)
    return () => { close(); clearInterval(iv) }
  }, [wish.id])

  const graph = wish.prd?.buildGraph || []
  const done = Object.values(steps as any).filter((s:any)=>s.status==='done').length
  const total = graph.length || Object.keys(steps).length

  return (
    <div className="build-compact">
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <strong style={{ fontFamily: 'Space Grotesk', fontWeight: 500 }}>{wish.prd?.appName || 'Building'}</strong>
          <span style={{ fontSize: 11, padding: '4px 8px', borderRadius: 999, background: 'rgba(139,92,246,0.12)', border: '1px solid rgba(139,92,246,0.18)', color: 'var(--intara-nebula-light)' }}>building {done}/{total}</span>
        </div>
        {!compact && <div style={{ color: 'var(--intara-faint)', fontSize: 12, marginTop: 4 }}>{wish.prompt}</div>}
        <div style={{ marginTop: 10, height: 6, background: 'rgba(255,255,255,0.06)', borderRadius: 999, overflow: 'hidden' }}>
          <div style={{ width: `${total ? (done/total)*100 : 0}%`, height: '100%', background: 'linear-gradient(90deg, #8B5CF6, #7C3AED)', transition: 'width 0.6s var(--ease-premium)' }} />
        </div>
      </div>

      <div className="glass" style={{ padding: 16, borderRadius: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)', marginBottom: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Build pipeline — DAG</span>
          <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: '-0.01em', fontSize: 10.5, color: 'var(--intara-dim)' }}>{done} / {total} steps · {graph.filter((n:any)=>n.kind==='frontend_page').length} pages · {graph.filter((n:any)=>n.kind==='backend_table').length} tables</span>
        </div>
        {/* DAG flowchart — CSS grid, no D3 */}
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12, padding: '10px 12px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)', borderRadius: 12 }}>
          {graph.map((n:any, idx:number) => {
            const st = steps[n.id] || { status: 'pending' }
            const isRunning = st.status === 'running'
            return (
              <span key={n.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <span style={{
                  padding: '6px 10px', borderRadius: 999, fontSize: 11, fontWeight: isRunning ? 600 : 500,
                  background: st.status==='done' ? 'rgba(16,185,129,0.12)' : isRunning ? 'rgba(139,92,246,0.16)' : st.status==='failed' ? 'rgba(248,113,113,0.12)' : 'rgba(255,255,255,0.04)',
                  border: `1px solid ${st.status==='done' ? 'rgba(16,185,129,0.22)' : isRunning ? 'rgba(139,92,246,0.32)' : 'rgba(255,255,255,0.06)'}`,
                  color: st.status==='done' ? '#10B981' : isRunning ? 'var(--intara-nebula-light)' : st.status==='failed' ? '#F87171' : 'var(--intara-faint)',
                  boxShadow: isRunning ? '0 0 12px rgba(139,92,246,0.3)' : 'none',
                  animation: isRunning ? 'pulse 1.2s ease-in-out infinite' : 'none',
                  whiteSpace: 'nowrap'
                }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: st.status==='done' ? '#10B981' : isRunning ? '#8B5CF6' : st.status==='failed' ? '#F87171' : 'var(--intara-dim)', display: 'inline-block', marginRight: 6, verticalAlign: 'middle', boxShadow: isRunning ? '0 0 6px #8B5CF6' : 'none' }} />
                  {n.id.replace('backend-','be:').replace('frontend-','fe:')}
                </span>
                {idx < graph.length - 1 && <span style={{ color: 'var(--intara-dim)', fontSize: 10, margin: '0 2px' }}>→</span>}
              </span>
            )
          })}
        </div>
        <div style={{ display: 'grid', gap: 8 }}>
          {graph.map((n:any) => {
            const st = steps[n.id] || { status: 'pending' }
            const color = st.status === 'done' ? '#10B981' : st.status === 'running' ? '#8B5CF6' : st.status === 'failed' ? '#F87171' : 'var(--intara-dim)'
            const bg = st.status === 'done' ? 'rgba(16,185,129,0.10)' : st.status === 'running' ? 'rgba(139,92,246,0.12)' : st.status === 'failed' ? 'rgba(248,113,113,0.08)' : 'rgba(255,255,255,0.02)'
            const isRunning = st.status === 'running'
            return (
              <div key={n.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', borderRadius: 12, background: bg, border: '1px solid rgba(255,255,255,0.04)', opacity: isRunning ? 1 : st.status === 'pending' ? 0.7 : 1 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, boxShadow: isRunning ? '0 0 8px rgba(139,92,246,0.5)' : 'none', flexShrink: 0, animation: isRunning ? 'pulse 1s infinite' : 'none' }} />
                <span style={{ fontSize: 12, fontWeight: 550, color: 'var(--intara-text)' }}>{n.id}</span>
                <span style={{ fontSize: 11, color: 'var(--intara-faint)' }}>{n.kind} · {n.ref || '-'}</span>
                <span style={{ marginLeft: 'auto', fontSize: 11, fontWeight: 500, color, display: 'flex', alignItems: 'center', gap: 6 }}>
                  {isRunning && <span style={{ width: 10, height: 10, border: '1.5px solid rgba(139,92,246,0.3)', borderTopColor: '#8B5CF6', borderRadius: '50%', display: 'inline-block', animation: 'spin 0.7s linear infinite' }} />}
                  {st.status}
                  {st.status === 'failed' && <button onClick={async()=>{await fetch(`/api/wish/${wish.id}/retry`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({stepId: n.id})}); window.location.reload()}} style={{ marginLeft: 8, padding: '4px 8px', borderRadius: 999, fontSize: 10, border: '1px solid rgba(248,113,113,0.3)', background: 'rgba(248,113,113,0.12)', color: '#F87171', cursor: 'pointer' }}>Retry</button>}
                </span>
              </div>
            )
          })}
        </div>
        <style>{`@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.7; } } @keyframes spin { to { transform: rotate(360deg); } }`}</style>
        <div style={{ marginTop: 10, fontSize: 11, color: 'var(--intara-dim)', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <span>● One prompt per page/component</span>
          <span>● Wired as single app at the end</span>
          <span>● SSE live + poll fallback</span>
        </div>
      </div>

      <div style={{ marginTop: 12, fontSize: 11, color: 'var(--intara-dim)' }}>Building sequentially — this takes ~6-10s for 12 steps. Do not close.</div>
    </div>
  )
}
