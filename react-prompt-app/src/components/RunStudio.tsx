/**
 * RunStudio — the product surface for a v2 build.
 *
 * A run is a prompt → typed App Spec → prebuilt-block runtime app. This view
 * keeps the app first: live preview, one-line change requests, and a spec /
 * activity inspector underneath. No generated application code is involved.
 */
import { Suspense, lazy, useEffect, useState } from 'react'
import { approveRun, chatRun, getEventlog, getRun, retryRun, streamRun } from '../api/client'
import { buildAppProjectZip, downloadBlob } from '../lib/zip'

const RuntimePreview = lazy(() => import('../runtime/RuntimePreview').then(m => ({ default: m.RuntimePreview })))
const VersionTimeline = lazy(() => import('./VersionTimeline').then(m => ({ default: m.VersionTimeline })))

const STAGES = [
  ['s0', 'Intake'],
  ['s1', 'Clarify'],
  ['s2', 'Model'],
  ['s3', 'Screens'],
  ['s4', 'Logic'],
  ['s5', 'Assemble'],
  ['s6', 'Seed'],
] as const

const TERMINAL = new Set(['done', 'degraded', 'failed', 'cancelled'])

function labelFor(status: string) {
  return status.replace(/_/g, ' ')
}

function Card({ title, children }: { title: string; children: any }) {
  return (
    <div className="glass" style={{ padding: '12px 14px', borderRadius: 14, minWidth: 0, width: '100%', boxSizing: 'border-box', overflow: 'hidden' }}>
      <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)', marginBottom: 8 }}>{title}</div>
      {children}
    </div>
  )
}

function StageRail({ steps }: { steps: any[] }) {
  const byKey = Object.fromEntries((steps || []).map((s: any) => [s.step_key, s]))
  return (
    <div className="run-stages">
      {STAGES.map(([key, label], i) => {
        const step = byKey[key]
        const state = step?.status || 'pending'
        return (
          <div key={key} className={`run-stage run-stage-${state}`}>
            <div className="run-stage-dot" aria-hidden="true">{state === 'done' ? '✓' : state === 'failed' ? '!' : i + 1}</div>
            <div style={{ minWidth: 0 }}>
              <div className="run-stage-label">{label}</div>
              <div className="run-stage-meta">{state === 'pending' ? 'queued' : labelFor(state)}</div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function RunStudio({ runId }: { runId: string }) {
  const [data, setData] = useState<any>(null)
  const [tab, setTab] = useState<'app' | 'spec' | 'activity'>('app')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [instruction, setInstruction] = useState('')
  const [summary, setSummary] = useState('')
  const [approved, setApproved] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [events, setEvents] = useState<any[] | null>(null)
  const [pollKey, setPollKey] = useState(0)

  useEffect(() => {
    let alive = true
    let timer: ReturnType<typeof setTimeout> | null = null

    async function fetchLatest() {
      try {
        const next = await getRun(runId)
        if (!alive) return null
        setData(next)
        setErr(null)
        return next
      } catch (e: any) {
        if (!alive) return null
        const message = e.message || 'could not load run'
        setErr(message)
        return null
      }
    }

    fetchLatest()

    // Real-time SSE streaming for live progress and events
    const closeStream = streamRun(runId, (ev: any) => {
      if (!alive) return
      setEvents((prev) => (prev ? [...prev, ev] : [ev]))
      const evType = ev?.type
      if (
        evType === 'run_done' ||
        evType === 'run_started' ||
        evType === 'step_started' ||
        evType === 'step_finished' ||
        evType === 'step_degraded' ||
        evType === 'stage_output' ||
        evType === 'approved'
      ) {
        fetchLatest()
      }
    })

    // Low-frequency fallback poll in case of network drops
    async function fallbackPoll() {
      const next = await fetchLatest()
      if (!alive) return
      const state = next?.run?.status || 'running'
      if (!TERMINAL.has(state)) {
        timer = setTimeout(fallbackPoll, 3500)
      }
    }
    timer = setTimeout(fallbackPoll, 3500)

    return () => {
      alive = false
      closeStream()
      if (timer) clearTimeout(timer)
    }
  }, [runId, pollKey])

  async function approve() {
    setBusy(true); setErr(null)
    try {
      await approveRun(runId)
      setApproved(true)
    } catch (e: any) {
      setErr(e.message || 'approve failed')
    } finally { setBusy(false) }
  }

  async function retry() {
    setBusy(true); setErr(null); setSummary('')
    try {
      const wish = data?.wish || data?.run?.inputs?.wish
      const appName = data?.app_name || data?.run?.inputs?.app_name
      await retryRun(runId, { wish, app_name: appName })
      setData((d: any) => ({
        ...(d || {}),
        run: { ...(d?.run || {}), status: 'running', error: null },
      }))
      setEvents(null)
      setPollKey(k => k + 1)
    } catch (e: any) {
      setErr(e.message || 'retry failed')
    } finally { setBusy(false) }
  }

  async function handleDownloadCode() {
    if (!spec) return
    setDownloading(true)
    try {
      const { blob, filename } = await buildAppProjectZip(spec)
      downloadBlob(blob, filename)
    } catch (e: any) {
      alert('Could not download project code: ' + (e?.message || e))
    } finally {
      setDownloading(false)
    }
  }

  async function patch() {
    if (instruction.trim().length < 4) return
    setBusy(true); setErr(null); setSummary('')
    try {
      const r = await chatRun(runId, instruction.trim())
      setData((d: any) => ({ ...(d || {}), spec: r.spec, version_id: r.version_id }))
      setSummary(r.summary || 'Spec updated.')
      setInstruction('')
      setApproved(false)
    } catch (e: any) {
      setErr(e.message || 'change request failed')
    } finally { setBusy(false) }
  }

  async function openActivity() {
    setTab('activity')
    if (events === null) {
      try { setEvents(await getEventlog(runId)) } catch { setEvents([]) }
    }
  }

  const run = data?.run
  const status = run?.status || 'loading'
  const spec = data?.spec
  const versionId = data?.version_id || null
  const projectId = run?.project_id || null
  const steps = data?.steps || []
  const degraded = data?.degraded_steps || []
  const llmCalls = data?.llm_calls
  const entities = spec?.model?.entities || []
  const pages = spec?.ui?.pages || []
  const rules = spec?.access?.rules || []
  const automations = spec?.automations || []
  const appName = spec?.app?.name || data?.app_name || data?.run?.inputs?.app_name || (status === 'loading' ? 'Opening your wish' : 'Building your app')
  const tagline = spec?.app?.tagline || data?.wish || 'A typed spec, rendered by the Intara component runtime.'

  return (
    <div className="run-studio">
      <header className="run-head glass">
        <div className="run-head-main">
          <div style={{ minWidth: 0 }}>
            <div className="run-eyebrow">Intara spec studio</div>
            <h1 className="run-title">{appName}</h1>
            <p className="run-tagline">{tagline}</p>
          </div>
          <div className="run-head-actions">
            <span className={`pill status-${status}`}>{labelFor(status)}</span>
            {versionId && <span className="mono" style={{ fontSize: 11, color: 'var(--intara-faint)' }}>v{String(versionId).slice(0, 8)}</span>}
            {approved && <span style={{ fontSize: 11, color: '#6EE7B7' }}>Approved ✓</span>}
            {status === 'failed' ? (
              <button className="btn-primary btn-sm" onClick={retry} disabled={busy}>
                {busy ? 'Retrying…' : 'Retry build'}
              </button>
            ) : spec ? (
              <>
                <button
                  className="btn-secondary btn-sm"
                  onClick={handleDownloadCode}
                  disabled={downloading}
                  title="Download runnable React project with all code, schema & seed (.zip)"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
                >
                  <span>↓</span>
                  <span>{downloading ? 'Packing…' : 'Download Code'}</span>
                </button>
                <button className="btn-primary btn-sm" onClick={approve} disabled={busy || !versionId || approved}>
                  {approved ? 'Approved' : 'Approve version'}
                </button>
              </>
            ) : null}
          </div>
        </div>

        {spec && (
          <div className="run-command">
            <input
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') patch() }}
              placeholder="Ask for a change — e.g. “add a kanban view for tasks”"
              disabled={busy}
              aria-label="Ask for a spec change"
            />
            <button className="btn-primary btn-sm" onClick={patch} disabled={busy || instruction.trim().length < 4}>
              {busy ? 'Patching…' : 'Patch app'}
            </button>
          </div>
        )}
        {summary && <div className="run-note">{summary}</div>}
        {err && <div className="run-error">{err}</div>}

        <div className="run-tabs" role="tablist" aria-label="Run views">
          <button role="tab" aria-selected={tab === 'app'} className={tab === 'app' ? 'active' : ''} onClick={() => setTab('app')}>App</button>
          <button role="tab" aria-selected={tab === 'spec'} className={tab === 'spec' ? 'active' : ''} onClick={() => setTab('spec')}>Spec</button>
          <button role="tab" aria-selected={tab === 'activity'} className={tab === 'activity' ? 'active' : ''} onClick={openActivity}>Activity</button>
        </div>
      </header>

      {tab === 'app' && (
        <>
          {spec ? (
            <section className="run-app-frame">
              <div className="studio-browserbar glass" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingRight: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span className="studio-browser-dots"><i /><i /><i /></span>
                  <span className="studio-browser-addr">{(spec?.app?.name || 'app').toLowerCase().replace(/[^a-z0-9]+/g, '-')}.intara.app</span>
                  <span className="studio-browser-refresh">↻</span>
                </div>
                <button
                  className="btn-ghost btn-sm"
                  onClick={handleDownloadCode}
                  disabled={downloading}
                  title="Download complete standalone app project (.zip)"
                  style={{ fontSize: 11, padding: '3px 10px', borderRadius: 6, color: '#93C5FD', cursor: 'pointer', background: 'rgba(59,130,246,0.12)', border: '1px solid rgba(59,130,246,0.2)' }}
                >
                  ↓ {downloading ? 'Packing…' : 'Download Code (.zip)'}
                </button>
              </div>
              <div className="run-app-canvas">
                <Suspense fallback={<div className="glass" style={{ padding: 48, textAlign: 'center' }}>Loading app…</div>}>
                  <RuntimePreview spec={spec} storageKey={`intara-run-${runId}`} />
                </Suspense>
              </div>
            </section>
          ) : (
            <section className="glass run-build-card">
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <span className="run-pulse" aria-hidden="true" style={status === 'failed' ? { background: '#F87171', animation: 'none' } : undefined} />
                <div>
                  <div style={{ fontFamily: 'Space Grotesk', fontSize: 19 }}>
                    {status === 'failed' ? 'Build failed' : TERMINAL.has(status) ? 'Spec unavailable' : 'Weaving the App Spec'}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--intara-faint)', marginTop: 2 }}>
                    The LLM writes a typed spec; the runtime composes prebuilt blocks. No app code is generated.
                  </div>
                </div>
                {llmCalls !== null && llmCalls !== undefined && <span className="pill">{llmCalls} LLM calls</span>}
              </div>
              <StageRail steps={steps} />
              {run?.error && <div className="run-error" style={{ marginTop: 10 }}>{run.error}</div>}
              {degraded.length > 0 && (
                <div className="run-note" style={{ color: '#FCD34D' }}>Degraded fallbacks: {degraded.join(', ')}</div>
              )}
              {status === 'failed' && (
                <div style={{ marginTop: 12 }}>
                  <button className="btn-primary btn-sm" onClick={retry} disabled={busy}>
                    {busy ? 'Retrying…' : 'Retry build'}
                  </button>
                  <span className="run-small" style={{ marginLeft: 10 }}>
                    Reuses cached steps; only missing steps call the model.
                  </span>
                </div>
              )}
            </section>
          )}

          {spec && (
            <div className="run-summary-grid">
              <Card title="Data"><div className="run-big">{entities.length}</div><div className="run-small">entities · {(entities.reduce((n: number, e: any) => n + (e.fields || []).length, 0))} fields</div></Card>
              <Card title="Screens"><div className="run-big">{pages.length}</div><div className="run-small">pages · {pages.reduce((n: number, p: any) => n + (p.blocks || []).length, 0)} blocks</div></Card>
              <Card title="Access"><div className="run-big">{rules.length}</div><div className="run-small">rules · {(spec?.access?.roles || []).length} roles</div></Card>
              <Card title="Logic"><div className="run-big">{automations.length}</div><div className="run-small">automations</div></Card>
            </div>
          )}
        </>
      )}

      {tab === 'spec' && (
        <div style={{ display: 'grid', gap: 12, minWidth: 0, width: '100%', boxSizing: 'border-box' }}>
          {!spec && <div className="glass" style={{ padding: 20, color: 'var(--intara-faint)' }}>The spec appears when the run reaches assembly.</div>}
          {spec && (
            <>
              <div className="run-summary-grid">
                <Card title="Entities">
                  {(spec?.model?.entities || []).map((e: any) => (
                    <div key={e.id} className="run-line"><strong>{e.label || e.id}</strong><span>{(e.fields || []).map((f: any) => f.id).join(', ')}</span></div>
                  ))}
                </Card>
                <Card title="Pages">
                  {(spec?.ui?.pages || []).map((p: any) => (
                    <div key={p.id} className="run-line"><strong>{p.title || p.id}</strong><span>{p.route} · {(p.blocks || []).map((b: any) => b.type).join(', ')}</span></div>
                  ))}
                </Card>
                <Card title="Roles & rules">
                  {(spec?.access?.roles || []).map((r: any) => <div key={r.id} className="run-line"><strong>{r.id}</strong><span>{r.label || ''}</span></div>)}
                  {(spec?.access?.rules || []).slice(0, 8).map((r: any, i: number) => (
                    <div key={i} className="run-line"><strong>{r.role}</strong><span>{r.entity} · {(r.ops || []).join(', ')}</span></div>
                  ))}
                </Card>
                <Card title="Assumptions">
                  {(spec?.assumptions || []).map((a: any, i: number) => <div key={i} className="run-line">· <span>{String(a)}</span></div>)}
                  {(spec?.assumptions || []).length === 0 && <div className="run-small">None recorded.</div>}
                </Card>
              </div>
              <Card title="App Spec JSON & Code Export">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
                  <span className="run-small">The declarative blueprint and downloadable code project.</span>
                  <button
                    className="btn-primary btn-sm"
                    onClick={handleDownloadCode}
                    disabled={downloading}
                    style={{ flexShrink: 0 }}
                  >
                    ↓ {downloading ? 'Packing…' : 'Download Complete Code (.zip)'}
                  </button>
                </div>
                <pre className="mono run-pre">{JSON.stringify(spec, null, 2)}</pre>
              </Card>
              <Suspense fallback={null}>
                <VersionTimeline key={versionId || 'none'} projectId={projectId} onPick={(vid: string, s: any) => {
                  setData((d: any) => ({ ...(d || {}), spec: s, version_id: vid }))
                  setSummary('Viewing an older version — the next change branches from here.')
                  setApproved(false)
                }} />
              </Suspense>
            </>
          )}
        </div>
      )}

      {tab === 'activity' && (
        <div style={{ display: 'grid', gap: 12 }}>
          <Card title="Pipeline">
            <StageRail steps={steps} />
            {run?.error && <div className="run-error" style={{ marginTop: 10 }}>{run.error}</div>}
            {degraded.length > 0 && <div className="run-note" style={{ color: '#FCD34D', marginTop: 10 }}>Degraded fallbacks: {degraded.join(', ')}</div>}
            {llmCalls !== null && llmCalls !== undefined && <div className="run-small" style={{ marginTop: 10 }}>{llmCalls} LLM calls · {steps.length} recorded stages</div>}
          </Card>
          <Card title={`Events · ${events?.length ?? '…'}`}>
            <div className="mono run-events">
              {(events || []).map((e: any, i: number) => (
                <div key={i}><span style={{ color: 'var(--intara-nebula-light)' }}>{e.type}</span> <span style={{ color: 'var(--intara-faint)' }}>{JSON.stringify(e.payload || {}).slice(0, 160)}</span></div>
              ))}
              {events === null && <span className="run-small">Loading event log…</span>}
              {events?.length === 0 && <span className="run-small">No events recorded.</span>}
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}
