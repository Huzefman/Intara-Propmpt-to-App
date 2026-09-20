import { useParams, Link } from 'react-router-dom'
import { useWish } from '../hooks/useWish'
import { ArtifactVault } from '../components/ArtifactVault'
import { approvePlan, streamBuild } from '../api/client'
import { useEffect, useState } from 'react'

export function WishVault() {
  const { id } = useParams()
  const { wish, loading, err } = useWish(id)

  if (loading && !wish) return <div className="glass" style={{ padding: 40, textAlign: 'center', borderRadius: 20 }}>
    <div style={{ width: 32, height: 32, border: '2px solid rgba(255,255,255,0.06)', borderTopColor: 'var(--intara-nebula)', borderRadius: '50%', animation: 'spin 0.9s var(--ease-fluid) infinite', margin: '0 auto' }} />
    <div style={{ fontFamily: 'Space Grotesk', fontSize: 14, fontWeight: 500, letterSpacing: '-0.02em', marginTop: 16, color: 'var(--intara-text)' }}>Weaving stardust…</div>
    <div style={{ color: 'var(--intara-faint)', fontSize: 12.5, marginTop: 6, fontWeight: 400 }}>Intara is listening — this takes ~8s</div>
    <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
  </div>
  if (err) return <div className="glass" style={{ padding: 20, color: '#FCA5A5', borderRadius: 16 }}>{err} <Link to="/" style={{ color: 'var(--intara-nebula-light)' }}>Make another wish</Link></div>
  if (!wish) return <div className="glass" style={{ padding: 24, textAlign: 'center', color: 'var(--intara-faint)', borderRadius: 16 }}>Wish not found.</div>

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

  if (wish.status === 'failed') {
    return <div className="glass" style={{ padding: 20, color: '#FCA5A5', borderRadius: 16 }}>Intara failed to weave. Try again. <Link to="/" style={{ color: 'var(--intara-nebula-light)' }}>New wish</Link></div>
  }

  // Staged: awaiting approval
  if (wish.status === 'awaiting_approval') {
    return <PlanApprovalView wish={wish} />
  }

  // Staged: building (SSE + polling fallback)
  if (wish.status === 'building' || wish.status === 'approved') {
    return <BuildingView wish={wish} />
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
        <div style={{ display: 'flex', gap: 8, alignItems: 'start', paddingTop: 4 }}>
          <Link to="/constellation" className="btn-ghost" style={{ textDecoration: 'none', display: 'inline-block', padding: '10px 16px', fontSize: 12.5 }}>View constellation</Link>
        </div>
      </div>
      <ArtifactVault wish={wish} />
    </div>
  )
}

function PlanApprovalView({ wish }: { wish: any }) {
  const [approving, setApproving] = useState(false)
  const prd = wish.prd || {}
  const graph = prd.buildGraph || []
  const req = prd.requirements || {}
  const ia = prd.ia || {}

  async function onApprove() {
    setApproving(true)
    try {
      await approvePlan(wish.id)
      // will be polling via useWish, but force reload
      window.location.reload()
    } catch (e: any) {
      alert(e.message)
      setApproving(false)
    }
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Link to="/" style={{ fontSize: 11.5, color: 'var(--intara-faint)', textDecoration: 'none' }}>← New wish</Link>
        <div style={{ fontFamily: 'Space Grotesk', fontSize: 24, fontWeight: 400, letterSpacing: '-0.03em', marginTop: 8 }}>{prd.appName || 'Plan'} <span style={{ fontSize: 12, fontWeight: 400, color: 'var(--intara-faint)', border: '1px solid rgba(255,255,255,0.06)', padding: '3px 8px', borderRadius: 999, marginLeft: 8 }}>awaiting approval</span></div>
        <div style={{ color: 'var(--intara-faint)', fontSize: 12.5, marginTop: 6, maxWidth: 640 }}>{wish.prompt}</div>
        <div style={{ color: 'var(--intara-muted)', fontSize: 12, marginTop: 6, fontStyle: 'italic' }}>{prd.tagline}</div>
      </div>

      <div className="glass" style={{ padding: 18, marginBottom: 14, borderRadius: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)' }}>Requirements</div>
        <div style={{ marginTop: 10 }}>
          {(req.functional || []).map((r: string, i: number) => (
            <div key={i} style={{ fontSize: 12.5, color: 'var(--intara-text)', padding: '6px 0', borderBottom: i + 1 < (req.functional?.length || 0) ? '1px solid rgba(255,255,255,0.04)' : 'none', display: 'flex', gap: 8 }}>
              <span style={{ color: 'var(--intara-nebula-light)', fontWeight: 600 }}>{i + 1}.</span> <span>{r}</span>
            </div>
          ))}
        </div>
        {req.nonFunctional && <div style={{ marginTop: 10, fontSize: 11, color: 'var(--intara-dim)' }}>Non-functional: {req.nonFunctional.join(' · ')}</div>}
        <div style={{ marginTop: 8, fontSize: 11, color: 'var(--intara-faint)' }}>Auth: {String(prd.auth)} · Roles: {(req.roles || []).join(', ')}</div>
      </div>

      <div className="glass" style={{ padding: 18, marginBottom: 14, borderRadius: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)' }}>Information Architecture</div>
        <div style={{ marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {(ia.entities || prd.tables?.map((t:any)=>t.name) || []).map((e: string) => (
            <span key={e} style={{ fontSize: 11, padding: '5px 10px', borderRadius: 999, background: 'rgba(139,92,246,0.10)', border: '1px solid rgba(139,92,246,0.18)', color: 'var(--intara-nebula-light)' }}>{e}</span>
          ))}
        </div>
        {ia.relations && <div style={{ marginTop: 8, fontSize: 11, color: 'var(--intara-faint)' }}>{ia.relations.join(' · ')}</div>}
        {ia.nav && <div style={{ marginTop: 6, fontSize: 11, color: 'var(--intara-dim)' }}>{ia.nav.join(' · ')}</div>}
      </div>

      <div className="glass" style={{ padding: 18, marginBottom: 14, borderRadius: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)' }}>Tables & Pages</div>
        <div style={{ marginTop: 10, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--intara-muted)', marginBottom: 6 }}>Tables ({(prd.tables||[]).length})</div>
            {(prd.tables||[]).map((t: any) => (
              <div key={t.name} style={{ fontSize: 11, padding: '6px 8px', marginBottom: 4, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)', borderRadius: 8 }}>
                <b style={{ color: 'var(--intara-text)' }}>{t.name}</b> <span style={{ color: 'var(--intara-faint)' }}>{t.fields.map((f:any)=>`${f.name}:${f.type}`).join(' · ')}</span>
              </div>
            ))}
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--intara-muted)', marginBottom: 6 }}>Pages ({(prd.pages||[]).length})</div>
            {(prd.pages||[]).map((p: any) => (
              <div key={p.name} style={{ fontSize: 11, padding: '6px 8px', marginBottom: 4, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)', borderRadius: 8 }}>
                <b style={{ color: 'var(--intara-text)' }}>{p.name}</b> <span style={{ color: 'var(--intara-faint)' }}>{p.route} · table:{p.table || '-'} · {p.components?.join(', ')}</span>
              </div>
            ))}
          </div>
        </div>
        <div style={{ marginTop: 10, fontSize: 11, color: 'var(--intara-faint)' }}>APIs: {(prd.apis||[]).map((a:any)=>`${a.method} ${a.path}`).join(' · ')}</div>
      </div>

      <div className="glass" style={{ padding: 18, marginBottom: 16, borderRadius: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)' }}>Build Graph — strict sequential</div>
        <div style={{ marginTop: 10, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {graph.map((n: any, idx: number) => (
            <span key={n.id} style={{ fontSize: 11, padding: '6px 10px', borderRadius: 999, background: idx===0 ? 'rgba(139,92,246,0.14)' : 'rgba(255,255,255,0.04)', border: '1px solid ' + (idx===0 ? 'rgba(139,92,246,0.22)' : 'rgba(255,255,255,0.06)'), color: idx===0 ? 'var(--intara-nebula-light)' : 'var(--intara-faint)' }}>
              {idx+1}. {n.id} <span style={{ opacity: 0.6 }}>({n.kind})</span>
            </span>
          ))}
        </div>
        <div style={{ marginTop: 8, fontSize: 11, color: 'var(--intara-dim)' }}>One prompt per page/component → wired as single app · Strict sequential, 1 LLM call at a time (free-tier safe) · SSE live</div>
      </div>

      <div style={{ display: 'flex', gap: 10 }}>
        <button onClick={onApprove} disabled={approving} className="btn-primary" style={{ padding: '12px 20px' }}>{approving ? 'Approving…' : 'Approve & Build →'}</button>
        <Link to="/" className="btn-ghost" style={{ textDecoration: 'none', padding: '12px 16px' }}>Edit prompt</Link>
      </div>
      <div style={{ marginTop: 8, fontSize: 11, color: 'var(--intara-dim)' }}>You can edit the plan JSON via PATCH /api/wish/{wish.id}/plan before approving (advanced).</div>
    </div>
  )
}

function BuildingView({ wish }: { wish: any }) {
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
    <div>
      <div style={{ marginBottom: 16 }}>
        <Link to="/" style={{ fontSize: 11.5, color: 'var(--intara-faint)', textDecoration: 'none' }}>← New wish</Link>
        <div style={{ fontFamily: 'Space Grotesk', fontSize: 22, fontWeight: 400, letterSpacing: '-0.03em', marginTop: 8 }}>{wish.prd?.appName || 'Building'} <span style={{ fontSize: 11, padding: '4px 8px', borderRadius: 999, background: 'rgba(139,92,246,0.12)', border: '1px solid rgba(139,92,246,0.18)', color: 'var(--intara-nebula-light)', marginLeft: 8 }}>building {done}/{total}</span></div>
        <div style={{ color: 'var(--intara-faint)', fontSize: 12, marginTop: 4 }}>{wish.prompt}</div>
        <div style={{ marginTop: 12, height: 6, background: 'rgba(255,255,255,0.06)', borderRadius: 999, overflow: 'hidden' }}>
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
