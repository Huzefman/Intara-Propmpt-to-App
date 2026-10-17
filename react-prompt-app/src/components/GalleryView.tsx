/**
 * Template gallery (Phase 9, slice 2): the gold specs, browsable with live
 * RuntimePreview and one-click similar builds. Reads the exemplars table
 * (service-key, server side) — never hardcodes the catalog.
 * Portfolio packaging: in static demo (VITE_DEMO=1) or when the API is
 * unreachable, the same 10 gold specs are served from the bundled
 * packages/spec/exemplars — offline gallery, every app still operable.
 */
import { Suspense, lazy, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getExemplar, getExemplars, startRun } from '../api/client'
import { DEMO } from '../demo'
import { DEMO_APPS, findDemoApp } from '../demo/exemplars'

const RuntimePreview = lazy(() => import('../runtime/RuntimePreview').then(m => ({ default: m.RuntimePreview })))

export function GalleryView() {
  const [items, setItems] = useState<any[]>([])
  const [active, setActive] = useState<any>(null)
  const [spec, setSpec] = useState<any>(null)
  const [err, setErr] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [offline, setOffline] = useState(DEMO)
  const navigate = useNavigate()

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
    setStarting(true); setErr(null)
    try {
      const wish = (active.spec?.app?.tagline || `A ${active.domain} app`).slice(0, 500)
      const r = await startRun(wish, active.spec?.app?.name || 'App')
      navigate(`/runs/${r.run_id}`)
    } catch (e: any) {
      setErr(e.message || 'start failed')
    } finally { setStarting(false) }
  }

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div className="glass" style={{ padding: '10px 14px', borderRadius: 14, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-nebula-light)' }}>✦ Templates · {items.length}</span>
        <span style={{ fontSize: 11, color: 'var(--intara-faint)' }}>{offline ? 'Static demo — every app runs in your browser (no backend, no LLM)' : 'Gold specs — preview live, build similar'}</span>
      </div>
      {offline && (
        <div className="glass" style={{ padding: '10px 14px', borderRadius: 14, fontSize: 11.5, color: 'var(--intara-muted)', lineHeight: 1.6 }}>
          These are the 10 human-reviewed gold specs from the eval suite. Everything below — tables, filters, kanban drag, roles, CSV, print — is executed by the spec runtime with sample data. The LLM build pipeline runs locally in the full Studio.
        </div>
      )}
      {err && <div className="glass" style={{ padding: 10, color: '#FDA4AF', fontSize: 12 }}>{err}</div>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
        {items.map((t) => (
          <button key={t.name} onClick={() => open(t.name)}
            className="glass" style={{ padding: 14, borderRadius: 14, textAlign: 'left', cursor: 'pointer', border: active?.name === t.name ? '1px solid rgba(139,92,246,0.9)' : undefined }}>
            <div style={{ fontSize: 14, fontWeight: 600 }}>{t.app || t.name}</div>
            <div style={{ fontSize: 11.5, color: 'var(--intara-muted)', margin: '4px 0' }}>{t.tagline}</div>
            <div className="mono" style={{ fontSize: 11, color: 'var(--intara-faint)' }}>{t.domain} · {t.entities} entities · {t.pages} pages</div>
          </button>
        ))}
      </div>
      {spec && (
        <div className="glass" style={{ padding: '12px 14px', borderRadius: 14 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8, flexWrap: 'wrap' }}>
            <strong>{active?.app}</strong>
            <span style={{ flex: 1 }} />
            {!offline && (
              <button className="btn-primary btn-sm" disabled={starting} onClick={buildSimilar}>
                {starting ? 'Starting…' : 'Build similar ✦'}
              </button>
            )}
          </div>
          <Suspense fallback={<div style={{ padding: 20, textAlign: 'center' }}>Loading app…</div>}>
            <RuntimePreview key={spec.app.name} spec={spec} />
          </Suspense>
        </div>
      )}
    </div>
  )
}
