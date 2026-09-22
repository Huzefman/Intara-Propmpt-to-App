import { Suspense, lazy, useEffect, useMemo, useState } from 'react'
import type { Wish } from '../api/client'
import type { Artifacts } from '../lib/zip'
import { Code } from './ArtifactVault'
const PreviewTrial = lazy(() => import('./PreviewTrial').then(m => ({ default: m.PreviewTrial })))

type CodeFile = { path: string; content: string; lang: string }

function collectFiles(artifacts: any, prd: any): CodeFile[] {
  const files: CodeFile[] = []
  const tables = artifacts.schema?.tables || prd.tables || []
  if (artifacts.schema || tables.length) {
    files.push({ path: 'schema.json', content: JSON.stringify({ tables }, null, 2), lang: 'json' })
    if (artifacts.schema?.prisma) files.push({ path: 'schema.prisma', content: artifacts.schema.prisma, lang: 'prisma' })
    if (artifacts.schema?.sql) files.push({ path: 'supabase.sql', content: artifacts.schema.sql, lang: 'sql' })
  }
  for (const f of (artifacts.frontend?.files || [])) {
    files.push({ path: f.path, content: f.content || '', lang: 'tsx' })
  }
  for (const f of (artifacts.backend?.files || [])) {
    files.push({ path: f.path, content: f.content || '', lang: 'py' })
  }
  if (artifacts.backend?.requirements) files.push({ path: 'requirements.txt', content: artifacts.backend.requirements, lang: 'txt' })
  const openapi = artifacts.backend?.openapi || artifacts.spec?.openapi
  if (openapi) files.push({ path: 'openapi.json', content: JSON.stringify(openapi, null, 2), lang: 'json' })
  if (artifacts.spec?.readme) files.push({ path: 'README.md', content: artifacts.spec.readme, lang: 'markdown' })
  return files
}

function stepLogLines(wish: Wish): { id: string; status: string; label: string }[] {
  const graph = wish.prd?.buildGraph || []
  const steps = wish.artifacts?.steps || {}
  return graph.map((n: any) => {
    const st = steps[n.id]?.status || 'pending'
    const label = n.kind === 'backend_table' ? `table ${n.ref}` : n.kind === 'frontend_page' ? `page ${n.ref}` : n.kind
    return { id: n.id, status: st, label: `${n.id} — ${label}` }
  })
}

export function StudioPreview({ wish }: { wish: Wish }) {
  const [expanded, setExpanded] = useState(false)
  const [mode, setMode] = useState<'preview' | 'code'>('preview')
  const [menuOpen, setMenuOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [activePath, setActivePath] = useState<string | null>(null)
  useEffect(() => {
    const open = () => {
      setMode('code')
      document.querySelector<HTMLElement>('.studio-preview')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
    window.addEventListener('studio:code', open)
    return () => window.removeEventListener('studio:code', open)
  }, [])
  const artifacts = wish.artifacts || {}
  const prd = wish.prd || {}
  const hasTrial = !!(artifacts.preview || artifacts.frontend || artifacts.schema)
  const slug = (prd.appName || 'intara-app').toLowerCase().replace(/[^a-z0-9]+/g, '') || 'intara-app'

  const files = useMemo(() => collectFiles(artifacts, prd), [wish.id, wish.status])
  const visible = query ? files.filter(f => f.path.toLowerCase().includes(query.toLowerCase())) : files
  const active = files.find(f => f.path === activePath) || files.find(f => f.path === 'README.md') || files[0] || null
  const logs = useMemo(() => stepLogLines(wish), [wish.id, wish.status, JSON.stringify(wish.artifacts?.steps || {})])

  async function onZip() {
    if (!artifacts.schema) return
    const { buildWishZip, downloadBlob } = await import('../lib/zip')
    const { blob, filename } = await buildWishZip(artifacts as Artifacts, prd.appName || 'Intara Wish')
    downloadBlob(blob, filename)
  }

  return (
    <section className={`studio-preview ${expanded ? 'expanded' : ''}`} aria-label={mode === 'preview' ? 'Live preview' : 'Code'}>
      <header className="studio-preview-bar glass">
        <div className="studio-seg" role="tablist" aria-label="Preview or code">
          <button role="tab" aria-selected={mode === 'preview'} className={mode === 'preview' ? 'active' : ''} onClick={() => setMode('preview')}>
            <span aria-hidden="true">👁</span> Preview
          </button>
          <button role="tab" aria-selected={mode === 'code'} className={mode === 'code' ? 'active' : ''} onClick={() => setMode('code')}>
            <span aria-hidden="true">&lt;/&gt;</span> Code
          </button>
        </div>
        <span className={`pill status-${wish.status}`}>{wish.status.replace('_', ' ')}</span>
        <button className="btn-ghost btn-sm" onClick={() => setExpanded(v => !v)} aria-expanded={expanded}>{expanded ? 'Exit full screen' : '⛶ Full screen'}</button>
        <div className="studio-menu-wrap">
          <button className="btn-ghost btn-sm" onClick={() => setMenuOpen(v => !v)} aria-expanded={menuOpen} aria-label="More actions">···</button>
          {menuOpen && (
            <div className="studio-menu glass" role="menu">
              <button role="menuitem" onClick={() => { navigator.clipboard.writeText(window.location.href); setMenuOpen(false) }}>Copy link</button>
              <button role="menuitem" onClick={() => { onZip(); setMenuOpen(false) }} disabled={!artifacts.schema}>Download zip</button>
            </div>
          )}
        </div>
        <span style={{ flex: 1 }} />
        <button className="btn-primary btn-sm" onClick={onZip} disabled={!artifacts.schema}>Download zip</button>
      </header>

      {mode === 'preview' ? (
        <div className="studio-preview-body">
          {hasTrial ? (
            <>
              <div className="studio-browserbar glass" aria-hidden="true">
                <span className="studio-browser-dots"><i /><i /><i /></span>
                <span className="studio-browser-addr">{slug}.app</span>
                <span className="studio-browser-refresh">↻</span>
              </div>
              <Suspense fallback={<div className="glass sandpack-shimmer" style={{ padding: 28, textAlign: 'center', color: 'var(--intara-muted)' }}>Warming up the trial sandbox…</div>}>
                <PreviewTrial artifacts={artifacts} appName={prd.appName || 'Intara Wish'} />
              </Suspense>
            </>
          ) : (
            <div className="studio-preview-empty glass">
              <div className="studio-preview-orb" aria-hidden="true">✦</div>
              <p><strong>Live preview appears here</strong></p>
              <p className="muted">Approve the plan and the trial app materializes in this pane while you watch the agent work.</p>
            </div>
          )}
        </div>
      ) : (
        <div className="studio-codeview">
          {files.length === 0 ? (
            <div className="studio-preview-empty glass">
              <p><strong>No code yet</strong></p>
              <p className="muted">Files land here as each build step completes.</p>
            </div>
          ) : (
            <>
              <div className="studio-code-main">
                <aside className="studio-explorer glass" aria-label="File explorer">
                  <div className="studio-explorer-head">Explorer</div>
                  <input
                    className="studio-explorer-search"
                    placeholder="Search files…"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    aria-label="Search files"
                  />
                  <div className="studio-explorer-list">
                    {visible.map(f => (
                      <button
                        key={f.path}
                        className={`studio-file ${active?.path === f.path ? 'active' : ''}`}
                        onClick={() => setActivePath(f.path)}
                      >
                        {f.path}
                      </button>
                    ))}
                    {visible.length === 0 && <div className="muted" style={{ padding: 8, fontSize: 12 }}>No matches.</div>}
                  </div>
                  <div className="studio-explorer-count mono">Files · {files.length}</div>
                </aside>
                <div className="studio-viewer">
                  {active ? (
                    <Code key={active.path} title={active.path} content={active.content} lang={active.lang} />
                  ) : (
                    <div className="muted" style={{ padding: 20, fontSize: 12.5 }}>Select a file.</div>
                  )}
                </div>
              </div>
              {logs.length > 0 && (
                <div className="studio-logs glass" aria-label="Build logs">
                  <div className="studio-logs-head mono">Logs</div>
                  <div className="studio-logs-list">
                    {logs.map(l => (
                      <div key={l.id} className="studio-log-line mono">
                        <span className={`studio-log-dot status-${l.status}`} aria-hidden="true" />
                        <span className="studio-log-id">{l.id}</span>
                        <span className="studio-log-status">{l.status}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </section>
  )
}
