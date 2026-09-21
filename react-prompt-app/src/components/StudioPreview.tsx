import { Suspense, lazy, useState } from 'react'
import type { Wish } from '../api/client'
import type { Artifacts } from '../lib/zip'
const PreviewTrial = lazy(() => import('./PreviewTrial').then(m => ({ default: m.PreviewTrial })))
const VaultLazy = lazy(() => import('./ArtifactVault').then(m => ({ default: m.ArtifactVault })))

export function StudioPreview({ wish }: { wish: Wish }) {
  const [expanded, setExpanded] = useState(false)
  const [inspect, setInspect] = useState(false)
  const artifacts = wish.artifacts || {}
  const prd = wish.prd || {}
  const hasTrial = !!(artifacts.preview || artifacts.frontend || artifacts.schema)
  const feCount = Object.keys(artifacts.frontend || {}).length
  const beCount = Object.keys(artifacts.backend || {}).length

  async function onZip() {
    if (!artifacts.schema) return
    const { buildWishZip, downloadBlob } = await import('../lib/zip')
    const { blob, filename } = await buildWishZip(artifacts as Artifacts, prd.appName || 'Intara Wish')
    downloadBlob(blob, filename)
  }

  const body = (
    <div className="studio-preview-body">
      {hasTrial ? (
        <Suspense fallback={<div className="glass sandpack-shimmer" style={{ padding: 28, textAlign: 'center', color: 'var(--intara-muted)' }}>Warming up the trial sandbox…</div>}>
          <PreviewTrial artifacts={artifacts} appName={prd.appName || 'Intara Wish'} />
        </Suspense>
      ) : (
        <div className="studio-preview-empty glass">
          <div className="studio-preview-orb" aria-hidden="true">✦</div>
          <p><strong>Live preview appears here</strong></p>
          <p className="muted">Approve the plan and the trial app materializes in this pane while you watch the agent work.</p>
        </div>
      )}
      {(wish.status === 'ready' || hasTrial) && (
        <div className="studio-preview-meta">
          <span className="pill">Version 1</span>
          {feCount > 0 && <span className="pill">{feCount} frontend files</span>}
          {beCount > 0 && <span className="pill">{beCount} backend files</span>}
          <span style={{ flex: 1 }} />
          <button className="btn-ghost btn-sm" onClick={() => setInspect(v => !v)} aria-expanded={inspect}>{inspect ? 'Hide code' : 'Inspect code'}</button>
        </div>
      )}
      {inspect && (wish.status === 'ready' || hasTrial) && (
        <Suspense fallback={<div className="muted">Loading vault…</div>}>
          <VaultLazy wish={wish} hideTrial />
        </Suspense>
      )}
    </div>
  )

  return (
    <section className={`studio-preview ${expanded ? 'expanded' : ''}`} aria-label="Live preview">
      <header className="studio-preview-bar glass">
        <span className="studio-preview-dot" aria-hidden="true" />
        <strong>Live Preview</strong>
        <span className={`pill status-${wish.status}`}>{wish.status.replace('_', ' ')}</span>
        <span style={{ flex: 1 }} />
        <button className="btn-ghost btn-sm" onClick={() => { navigator.clipboard.writeText(window.location.href); }}>Share</button>
        <button className="btn-ghost btn-sm" onClick={onZip} disabled={!artifacts.schema}>Download zip</button>
        <button className="btn-ghost btn-sm" onClick={() => setExpanded(v => !v)} aria-expanded={expanded}>{expanded ? 'Exit full screen' : 'Full screen'}</button>
      </header>
      {body}
    </section>
  )
}
