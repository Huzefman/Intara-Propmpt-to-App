/**
 * Template gallery (Phase 9, slice 2): the gold specs, browsable with live
 * RuntimePreview and one-click similar builds. Reads the exemplars table
 * (service-key, server side) — never hardcodes the catalog.
 * Portfolio packaging: in static demo (VITE_DEMO=1) or when the API is
 * unreachable, the same 10 gold specs are served from the bundled
 * packages/spec/exemplars — offline gallery, every app still operable.
 */
import { Suspense, lazy, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getExemplar, getExemplars, createWishShell, startRun } from '../api/client'
import { DEMO } from '../demo'
import { useAuth } from '../hooks/useAuth'
import { DEMO_APPS, findDemoApp } from '../demo/exemplars'

const RuntimePreview = lazy(() => import('../runtime/RuntimePreview').then(m => ({ default: m.RuntimePreview })))

/**
 * Gallery data is deliberately not global. Each browser tab gets a session
 * id, and the authenticated account (or "guest") gets its own namespace, so
 * edits are visible only to that account in that session. Closing the tab
 * therefore abandons the demo database instead of leaving a permanent change.
 */
function galleryPreviewSession(): string {
  const key = 'intara-gallery-preview-session'
  try {
    const existing = sessionStorage.getItem(key)
    if (existing) return existing
    const id = typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`
    sessionStorage.setItem(key, id)
    return id
  } catch {
    // Storage can be blocked (private mode policies). A per-mount namespace
    // still keeps the preview ephemeral and isolated.
    return `${Date.now()}-${Math.random().toString(36).slice(2)}`
  }
}

function domainIcon(domain: string) {
  const d = (domain || '').toLowerCase()
  if (d.includes('health') || d.includes('clinic') || d.includes('vet')) return '🩺'
  if (d.includes('logistics') || d.includes('warehouse') || d.includes('stock')) return '📦'
  if (d.includes('finance') || d.includes('invoice') || d.includes('billing')) return '💳'
  if (d.includes('crm') || d.includes('client') || d.includes('sales')) return '💼'
  if (d.includes('task') || d.includes('habit') || d.includes('todo')) return '📋'
  if (d.includes('property') || d.includes('real')) return '🏡'
  if (d.includes('event') || d.includes('schedule')) return '📅'
  return '✦'
}

export function GalleryView() {
  const [items, setItems] = useState<any[]>([])
  const [active, setActive] = useState<any>(null)
  const [spec, setSpec] = useState<any>(null)
  const [err, setErr] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [offline, setOffline] = useState(DEMO)
  const navigate = useNavigate()
  const { user } = useAuth(!DEMO)
  const previewStorageKey = useMemo(
    () => `intara-gallery-${user?.id ?? 'guest'}-${galleryPreviewSession()}`,
    [user?.id],
  )

  useEffect(() => {
    if (DEMO) { setItems(DEMO_APPS); return }
    getExemplars()
      .then(setItems)
      .catch(() => { setItems(DEMO_APPS); setOffline(true) })
  }, [])

  async function open(name: string) {
    setErr(null)
    const local = findDemoApp(name)
    if (local && (DEMO || offline)) {
      setActive(local)
      setSpec(local.spec)
      return
    }
    try {
      const ex = await getExemplar(name)
      setActive(ex)
      setSpec(ex.spec)
    } catch (e: any) {
      setErr(e.message || 'load failed')
    }
  }

  async function buildSimilar() {
    if (!active) return
    if (!DEMO && !user) {
      navigate('/auth?mode=signup', { state: { from: '/templates' } })
      return
    }
    setStarting(true); setErr(null)
    try {
      const wish = (active.spec?.app?.tagline || `A ${active.domain} app`).slice(0, 500)
      const shell = await createWishShell(wish)
      const r = await startRun(wish, active.spec?.app?.name || 'App', shell.id)
      navigate(`/runs/${r.run_id}`)
    } catch (e: any) {
      setErr(e.message || 'start failed')
    } finally { setStarting(false) }
  }

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div className="glass" style={{ padding: '14px 18px', borderRadius: 16, display: 'flex', gap: 12, alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-nebula-light)' }}>✦ Production Exemplars</span>
            <span style={{ fontSize: 10.5, fontWeight: 550, padding: '2px 8px', borderRadius: 999, background: 'rgba(255,255,255,0.05)', color: 'var(--intara-muted)' }}>{items.length} apps</span>
          </div>
          <div style={{ fontSize: 12, color: 'var(--intara-faint)', marginTop: 4 }}>
            {offline ? 'Static demo — fully operable in-browser apps with persistent client state.' : 'Curated gold-standard apps — click to preview live or fork into your workspace.'}
          </div>
        </div>
        {active && !offline && (
          <button className="btn-primary btn-sm" disabled={starting} onClick={buildSimilar} style={{ padding: '8px 16px', fontSize: 12 }}>
            {starting ? 'Forking…' : `Fork ${active.app || active.name} ✦`}
          </button>
        )}
      </div>

      {err && <div className="glass" style={{ padding: 12, color: '#FDA4AF', fontSize: 12, borderRadius: 12 }}>{err}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 12 }}>
        {items.map((t) => {
          const isSel = active?.name === t.name
          return (
            <button
              key={t.name}
              onClick={() => open(t.name)}
              className={`template-card ${isSel ? 'active' : ''}`}
            >
              <div>
                <span className="template-tag">
                  <span>{domainIcon(t.domain)}</span>
                  <span>{t.domain || 'App'}</span>
                </span>
                <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--intara-text)', letterSpacing: '-0.02em', marginTop: 2 }}>{t.app || t.name}</div>
                <div style={{ fontSize: 11.5, color: 'var(--intara-muted)', margin: '6px 0 10px', lineHeight: 1.5 }}>{t.tagline}</div>
              </div>
              <div className="mono" style={{ fontSize: 10.5, color: 'var(--intara-faint)', display: 'flex', gap: 8, alignItems: 'center', borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: 8 }}>
                <span>{t.entities || 3} entities</span>
                <span>·</span>
                <span>{t.pages || 4} pages</span>
                {isSel && <span style={{ marginLeft: 'auto', color: 'var(--intara-nebula-light)', fontWeight: 600 }}>Active ✓</span>}
              </div>
            </button>
          )
        })}
      </div>

      {spec && (
        <div className="run-window-frame" style={{ marginTop: 8 }}>
          <div className="run-window-chrome">
            <div className="window-dots">
              <span className="window-dot dot-red" />
              <span className="window-dot dot-yellow" />
              <span className="window-dot dot-green" />
            </div>
            <div className="window-address-bar">
              <span className="window-lock">🔒</span>
              <span className="window-url">templates.intara.live</span>
              <span className="window-route">/{active?.name || 'app'}</span>
            </div>
            <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
              {!offline && (
                <button className="btn-primary btn-sm" disabled={starting} onClick={buildSimilar} style={{ padding: '5px 12px', fontSize: 11.5 }}>
                  {starting ? 'Building…' : 'Build Similar ✦'}
                </button>
              )}
            </div>
          </div>
          <div style={{ padding: 14, background: 'rgba(6,6,12,0.45)' }}>
            <Suspense fallback={<div style={{ padding: 32, textAlign: 'center', color: 'var(--intara-faint)' }}>Starting sandbox…</div>}>
              <RuntimePreview key={`${spec.app.name}:${previewStorageKey}`} spec={spec} storageKey={`${previewStorageKey}-${spec.app.name}`} />
            </Suspense>
          </div>
        </div>
      )}
    </div>
  )
}
