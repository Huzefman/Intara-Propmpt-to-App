import { useParams, Link } from 'react-router-dom'
import { useCallback } from 'react'
import { useWish } from '../hooks/useWish'
import { AgentThread } from '../components/AgentThread'
import { StudioPreview } from '../components/StudioPreview'
import { StudioRail } from '../components/StudioRail'
import { ArtifactVault } from '../components/ArtifactVault'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { streamBuild } from '../api/client'
import { getWish } from '../api/client'
import { useEffect, useRef, useState } from 'react'

export function WishVault() {
  const { id } = useParams()
  const { wish, loading, busy, err, setWish } = useWish(id)
  const refresh = useCallback(async () => {
    if (!id) return
    try { setWish(await getWish(id)) } catch { /* keep current */ }
  }, [id, setWish])
  // All hooks above every early return (Rules of Hooks)
  const [railCollapsed, setRailCollapsed] = useState(() => { try { return localStorage.getItem('studio.rail') === '1' } catch { return false } })
  const [chatCollapsed, setChatCollapsed] = useState(false)
  const clampW = (w: number) => Math.min(720, Math.max(280, Math.round(w)))
  const [chatWidth, setChatWidth] = useState(() => { try { const v = parseInt(localStorage.getItem('studio.chatw') || '400', 10); return clampW(Number.isFinite(v) ? v : 400) } catch { return 400 } })
  const [dragging, setDragging] = useState(false)
  const dragRef = useRef<{ startX: number; startW: number } | null>(null)
  const widthRef = useRef(chatWidth)
  function toggleRail() {
    setRailCollapsed(v => { try { localStorage.setItem('studio.rail', v ? '0' : '1') } catch {} return !v })
  }
  function onDividerDown(e: React.PointerEvent<HTMLDivElement>) {
    e.currentTarget.setPointerCapture?.(e.pointerId)
    dragRef.current = { startX: e.clientX, startW: widthRef.current }
    setDragging(true)
  }
  function onDividerMove(e: React.PointerEvent<HTMLDivElement>) {
    const d = dragRef.current
    if (!d) return
    const w = clampW(d.startW + (e.clientX - d.startX))
    widthRef.current = w
    setChatWidth(w)
  }
  function endDrag() {
    if (!dragRef.current) return
    dragRef.current = null
    setDragging(false)
    try { localStorage.setItem('studio.chatw', String(widthRef.current)) } catch {}
  }
  function onDividerKey(e: React.KeyboardEvent<HTMLDivElement>) {
    const step = e.shiftKey ? 48 : 16
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.preventDefault()
      const w = clampW(widthRef.current + (e.key === 'ArrowRight' ? step : -step))
      widthRef.current = w
      setChatWidth(w)
      try { localStorage.setItem('studio.chatw', String(w)) } catch {}
    } else if (e.key === 'Home') {
      e.preventDefault()
      widthRef.current = 400
      setChatWidth(400)
      try { localStorage.setItem('studio.chatw', '400') } catch {}
    }
  }

  if (loading && !wish) return <div className="glass" style={{ padding: 40, textAlign: 'center', borderRadius: 20 }}>
    <div style={{ width: 32, height: 32, border: '2px solid rgba(255,255,255,0.06)', borderTopColor: 'var(--intara-nebula)', borderRadius: '50%', animation: 'spin 0.9s var(--ease-fluid) infinite', margin: '0 auto' }} />
    <div style={{ fontFamily: 'Space Grotesk', fontSize: 14, fontWeight: 500, letterSpacing: '-0.02em', marginTop: 16, color: 'var(--intara-text)' }}>Opening studio…</div>
    <div style={{ color: 'var(--intara-faint)', fontSize: 12.5, marginTop: 6, fontWeight: 400 }}>{busy ? 'Server is busy building — holding the door open, retrying…' : 'Intara is listening'}</div>
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
        <ErrorBoundary label="artifact vault" key={`vault-${wish.id}`}>
          <ArtifactVault wish={wish} />
        </ErrorBoundary>
      </div>
    )
  }

  // Staged Studio: collapsible rail + chat + preview, edge-to-edge
  const appName = wish?.prd?.appName && wish.status !== 'planning' ? wish.prd.appName : 'New wish'
  return (
    <div
      className={`studio-shell ${railCollapsed ? 'rail-collapsed' : ''} ${chatCollapsed ? 'chat-collapsed' : ''}`}
      style={chatCollapsed ? undefined : { gridTemplateColumns: `auto ${chatWidth}px 8px minmax(0, 1fr)` }}
    >
      <StudioRail collapsed={railCollapsed} onToggle={toggleRail} />
      {!chatCollapsed ? (
        <div className="studio-thread-col">
          <div className="studio-thread-head">
            <div>
              <div className="studio-eyebrow">Studio&nbsp;&nbsp;›&nbsp;&nbsp;{wish.status === 'planning' ? 'Clarifying' : wish.status === 'awaiting_approval' ? 'Plan approval' : building ? 'Building' : wish.status.replace('_', ' ')}</div>
              <strong>{appName} <span className="studio-title-caret" aria-hidden="true">▾</span></strong>
            </div>
            <span className={`pill status-${wish.status}`}>{wish.status.replace('_', ' ')}</span>
            <button className="studio-collapse-btn" onClick={() => setChatCollapsed(true)} title="Collapse chat" aria-label="Collapse chat">‹‹</button>
          </div>
          <ErrorBoundary label="agent thread" key={`thread-${wish.id}-${wish.status}`}>
            <AgentThread wish={wish} onChanged={refresh} buildView={building ? <BuildingView wish={wish} compact onChanged={refresh} /> : undefined} />
          </ErrorBoundary>
        </div>
      ) : (
        <button className="studio-chat-reopen" onClick={() => setChatCollapsed(false)} aria-label="Reopen chat">
          <span aria-hidden="true">››</span>
          <span className="studio-chat-reopen-label">{appName}</span>
        </button>
      )}
      {!chatCollapsed && (
        <div
          className={`studio-divider ${dragging ? 'dragging' : ''}`}
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize chat and preview (arrow keys work too)"
          aria-valuenow={chatWidth}
          aria-valuemin={280}
          aria-valuemax={720}
          tabIndex={0}
          onPointerDown={onDividerDown}
          onPointerMove={onDividerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onKeyDown={onDividerKey}
        />
      )}
      <ErrorBoundary label="preview pane" key={`preview-${wish.id}-${wish.status}`}>
        <StudioPreview wish={wish} />
      </ErrorBoundary>
    </div>
  )
}

function fmtDur(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return '—'
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m ${s % 60}s`
}

function toMs(t: any): number | null {
  if (t == null) return null
  if (typeof t === 'number') return t < 1e12 ? t * 1000 : t
  const p = Date.parse(t)
  return Number.isFinite(p) ? p : null
}

function eventLabel(ev: any): { text: string; tone: 'ok' | 'busy' | 'bad' | 'dim' } {
  const d = ev.data || ev || {}
  switch (ev.event) {
    case 'snapshot': return { text: `Connected — ${(d.status || 'building').replace('_', ' ')}`, tone: 'dim' }
    case 'build_started': return { text: `Build started — ${(d.graph || []).length} steps`, tone: 'busy' }
    case 'step_started': return { text: `▶ ${d.stepId || ''} started (${d.kind || ''}${d.ref ? ` · ${d.ref}` : ''})`, tone: 'busy' }
    case 'step_done': return { text: `✓ ${d.stepId || ''} done`, tone: 'ok' }
    case 'step_failed': return { text: `✗ ${d.stepId || ''} failed — ${(d.error || '').slice(0, 140)}`, tone: 'bad' }
    case 'step_skipped': return { text: `↷ ${d.stepId || ''} already done — skipped`, tone: 'dim' }
    case 'validation_started': return { text: 'Running pre-checks (syntax + wiring)…', tone: 'busy' }
    case 'validation_warnings': return { text: `⚠ ${(d.errors || []).length} validation warning(s) — see details`, tone: 'bad' }
    case 'validation_gates': return { text: d.phase === 'tsc/vite' ? 'Heavy gates: type-check + production build (slowest step, minutes)…' : d.phase === 'import/crud' ? 'Heavy gates: backend import + CRUD matrix…' : `Gate phase: ${d.phase || ''}`, tone: 'busy' }
    case 'plan_phase': return { text: `Plan: ${d.label || d.phase || ''}`, tone: 'busy' }
    case 'plan_ready': return { text: 'Plan ready — awaiting approval', tone: 'ok' }
    case 'plan_failed': return { text: `Plan failed — ${(d.error || '').slice(0, 140)}`, tone: 'bad' }
    case 'build_done': return { text: 'Build done — packing the trial…', tone: 'ok' }
    case 'build_failed': return { text: `Build failed at ${d.failedStep || 'unknown step'}`, tone: 'bad' }
    case 'heartbeat': return { text: `Still working — status ${(d.status || '').replace('_', ' ')}`, tone: 'dim' }
    case 'error': return { text: `Stream note: ${(d.error || ev.error || '').slice(0, 140)}`, tone: 'dim' }
    default: return { text: `${ev.event}`, tone: 'dim' }
  }
}

function BuildingView({ wish, compact = false, onChanged }: { wish: any; compact?: boolean; onChanged?: () => void }) {
  const [steps, setSteps] = useState<any>(wish.artifacts?.steps || {})
  const [feed, setFeed] = useState<{ t: number; text: string; tone: string }[]>([])
  const [gatePhase, setGatePhase] = useState<string | null>(null)
  const [live, setLive] = useState<'live' | 'polling'>('live')
  const [now, setNow] = useState(() => Date.now())
  const [finished, setFinished] = useState<string | null>(null)
  const [retryErr, setRetryErr] = useState<string | null>(null)
  const [retrying, setRetrying] = useState<string | null>(null)
  const finishedRef = useRef(false)

  async function onRetryStep(stepId: string) {
    setRetryErr(null)
    setRetrying(stepId)
    try {
      const { retryStep } = await import('../api/client')
      await retryStep(wish.id, stepId)
      setFinished(null)
      finishedRef.current = false
      onChanged?.()
    } catch (e: any) {
      setRetryErr(e?.message || 'Retry failed')
    } finally {
      setRetrying(null)
    }
  }

  const pushFeed = useCallback((ev: any) => {
    const { text, tone } = eventLabel(ev)
    setFeed((prev) => [...prev.slice(-30), { t: Date.now(), text, tone }])
  }, [])

  const finish = useCallback((status: string) => {
    if (finishedRef.current) return
    finishedRef.current = true
    setFinished(status)
    pushFeed({ event: status === 'ready' ? 'build_done' : 'build_failed', data: {} })
    // refresh parent (no full page reload) so Trial/plan states render
    setTimeout(() => { try { onChanged?.() } catch {} }, 600)
  }, [onChanged, pushFeed])

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    // SSE live
    const close = streamBuild(wish.id, (ev: any) => {
      if (!ev || !ev.event) return
      if (ev.event === 'step_started' || ev.event === 'step_done' || ev.event === 'step_failed') {
        setSteps((prev: any) => ({ ...prev, [ev.data.stepId]: { status: ev.event === 'step_started' ? 'running' : ev.event === 'step_done' ? 'done' : 'failed', ...ev.data } }))
      } else if (ev.event === 'snapshot' && ev.data?.steps) {
        setSteps((prev: any) => ({ ...prev, ...ev.data.steps }))
      } else if (ev.event === 'validation_started') {
        setGatePhase('pre-checks')
      } else if (ev.event === 'validation_gates') {
        setGatePhase(ev.data?.phase || 'gates')
      } else if (ev.event === 'build_done') {
        finish('ready')
        return
      } else if (ev.event === 'build_failed' || ev.event === 'plan_failed') {
        finish('failed')
        return
      } else if (ev.event === 'error') {
        setLive('polling')
      }
      if (ev.event === 'heartbeat') {
        // collapse repeats: one "still working" line until real news arrives
        setFeed((prev) => {
          const last = prev[prev.length - 1]
          if (last && last.text.startsWith('Still working')) return prev
          const { text, tone } = eventLabel(ev)
          return [...prev.slice(-30), { t: Date.now(), text, tone }]
        })
      } else pushFeed(ev)
      setLive('live')
    })
    // polling fallback every 2s (also the source of truth while SSE is down)
    const iv = setInterval(async () => {
      try {
        const res = await fetch(`/api/wish/${wish.id}`)
        if (res.ok) {
          const data = await res.json()
          if (data.artifacts?.steps) setSteps(data.artifacts.steps)
          if (data.status === 'ready' || data.status === 'failed') {
            clearInterval(iv)
            finish(data.status)
          }
        }
      } catch { setLive('polling') }
    }, 2000)
    return () => { close(); clearInterval(iv) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wish.id])

  const graph = wish.prd?.buildGraph || []
  const stepList = Object.entries(steps as any)
  const done = stepList.filter(([, s]: any) => s?.status === 'done').length
  const total = graph.length || stepList.length
  const running = graph.find((n: any) => (steps[n.id] || {}).status === 'running')
  const runningDetail = running ? `${running.kind}${running.ref ? ` · ${running.ref}` : ''}${running.promptHint ? ` — ${running.promptHint}` : ''}` : null
  const failedSteps = graph.filter((n: any) => (steps[n.id] || {}).status === 'failed')
  const startedAll = stepList.map(([, s]: any) => toMs(s?.startedAt)).filter((v): v is number => v != null)
  const elapsed = startedAll.length ? now - Math.min(...startedAll) : 0
  const toneColor: Record<string, string> = { ok: '#10B981', busy: 'var(--intara-nebula-light)', bad: '#F87171', dim: 'var(--intara-dim)' }

  return (
    <div className="build-compact">
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <strong style={{ fontFamily: 'Space Grotesk', fontWeight: 500 }}>Building {wish.prd?.appName || 'app'}</strong>
          <span title={live === 'live' ? 'Live event stream connected' : 'Stream down — updating via polling'} style={{ fontSize: 10.5, padding: '3px 8px', borderRadius: 999, background: live === 'live' ? 'rgba(16,185,129,0.12)' : 'rgba(251,191,36,0.12)', border: '1px solid rgba(255,255,255,0.06)', color: live === 'live' ? '#10B981' : '#FBBF24' }}>
            ● {live === 'live' ? 'live' : 'polling'}
          </span>
          <span style={{ marginLeft: 'auto', fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: 'var(--intara-faint)' }}>{done} / {total} · {fmtDur(elapsed)}</span>
        </div>
        {!compact && <div style={{ color: 'var(--intara-faint)', fontSize: 12, marginTop: 4 }}>{wish.prompt}</div>}
        {(runningDetail || finished) && (
          <div style={{ marginTop: 8, fontSize: 12, color: finished ? (finished === 'ready' ? '#10B981' : '#F87171') : 'var(--intara-nebula-light)' }}>
            {finished ? (finished === 'ready' ? '✓ Build finished — packing the trial…' : '✗ Build stalled — plan is safe, retry below.') : (
              <><span className="chat-shimmer" aria-label="Step in progress">✦</span> Now building: {runningDetail}{gatePhase ? ` — ${gatePhase}` : ''}</>
            )}
          </div>
        )}
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
            const sMs = toMs(st.startedAt)
            const eMs = toMs(st.endedAt)
            const dur = sMs != null ? fmtDur((eMs ?? now) - sMs) : null
            return (
              <div key={n.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', borderRadius: 12, background: bg, border: '1px solid rgba(255,255,255,0.04)', opacity: isRunning ? 1 : st.status === 'pending' ? 0.7 : 1 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, boxShadow: isRunning ? '0 0 8px rgba(139,92,246,0.5)' : 'none', flexShrink: 0, animation: isRunning ? 'pulse 1s infinite' : 'none' }} />
                <span style={{ fontSize: 12, fontWeight: 550, color: 'var(--intara-text)' }}>{n.id}</span>
                <span style={{ fontSize: 11, color: 'var(--intara-faint)' }}>{n.kind} · {n.ref || '-'}{dur ? ` · ${dur}` : ''}</span>
                <span style={{ marginLeft: 'auto', fontSize: 11, fontWeight: 500, color, display: 'flex', alignItems: 'center', gap: 6 }}>
                  {isRunning && <span style={{ width: 10, height: 10, border: '1.5px solid rgba(139,92,246,0.3)', borderTopColor: '#8B5CF6', borderRadius: '50%', display: 'inline-block', animation: 'spin 0.7s linear infinite' }} />}
                  {st.status}
                  {st.status === 'done' && st.fallback_reason && (
                    <span title={String(st.fallback_reason).slice(0, 300)} style={{ padding: '3px 8px', borderRadius: 999, fontSize: 10, border: '1px solid rgba(251,191,36,0.3)', background: 'rgba(251,191,36,0.08)', color: '#FBBF24', whiteSpace: 'nowrap' }}>template fallback</span>
                  )}
                  {st.status === 'failed' && <button onClick={() => onRetryStep(n.id)} disabled={retrying === n.id} style={{ marginLeft: 8, padding: '4px 8px', borderRadius: 999, fontSize: 10, border: '1px solid rgba(248,113,113,0.3)', background: 'rgba(248,113,113,0.12)', color: '#F87171', cursor: 'pointer' }}>{retrying === n.id ? 'Retrying…' : 'Retry'}</button>}
                </span>
              </div>
            )
          })}
        </div>
        {failedSteps.length > 0 && (
          <div style={{ marginTop: 10, padding: '10px 12px', borderRadius: 12, background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.14)', fontSize: 11.5, color: '#FCA5A5' }}>
            {failedSteps.map((n:any) => (
              <div key={n.id} style={{ marginTop: 4 }}>{n.id}: {String((steps[n.id] || {}).error || 'failed').slice(0, 220)}</div>
            ))}
            {retryErr && <div style={{ marginTop: 6 }}>Retry note: {retryErr}</div>}
          </div>
        )}
        {feed.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)', marginBottom: 6 }}>Live activity</div>
            <div style={{ display: 'grid', gap: 4, maxHeight: 180, overflow: 'auto', padding: '10px 12px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)', borderRadius: 12 }}>
              {feed.slice(-8).map((f, i) => (
                <div key={i} style={{ fontSize: 11, fontFamily: 'JetBrains Mono, monospace', color: toneColor[f.tone] || 'var(--intara-dim)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  <span style={{ opacity: 0.6 }}>{new Date(f.t).toLocaleTimeString()}</span> {f.text}
                </div>
              ))}
            </div>
          </div>
        )}
        <style>{`@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.7; } } @keyframes spin { to { transform: rotate(360deg); } }`}</style>
        <div style={{ marginTop: 10, fontSize: 11, color: 'var(--intara-dim)', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <span>● Step-by-step, wired as one app at the end</span>
          <span>● Type-check + build gates are the slow part (minutes)</span>
          <span>● Safe to keep open — progress resumes after refresh</span>
        </div>
      </div>

      <div style={{ marginTop: 12, fontSize: 11, color: 'var(--intara-dim)' }}>Building sequentially on the shared free pool — quiet stretches of a few minutes during gates are normal.</div>
    </div>
  )
}
