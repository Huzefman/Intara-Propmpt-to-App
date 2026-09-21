import { useState, lazy, Suspense } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import type { Artifacts } from '../lib/zip'
const PreviewTrial = lazy(() => import('./PreviewTrial').then(m => ({ default: m.PreviewTrial })))

type Tab = 'trial' | 'schema' | 'frontend' | 'backend' | 'scroll'

export function ArtifactVault({ wish, hideTrial = false }: { wish: any; hideTrial?: boolean }) {
  const [tab, setTab] = useState<Tab>(hideTrial ? 'schema' : 'trial')
  const artifacts = wish.artifacts || {}
  const prd = wish.prd || {}
  const appName = prd.appName || 'Intara Wish'

  async function onZip() {
    if (!artifacts.schema) return
    const { buildWishZip, downloadBlob } = await import('../lib/zip')
    const { blob, filename } = await buildWishZip(artifacts as Artifacts, appName)
    downloadBlob(blob, filename)
  }

  const tabs: { id: Tab; label: string; glyph: string }[] = [
    ...(hideTrial ? [] : [{ id: 'trial' as Tab, label: 'Trial', glyph: '/assets/glyphs/frontend.png' }]),
    { id: 'schema', label: 'Schemas', glyph: '/assets/glyphs/schema.png' },
    { id: 'frontend', label: 'Frontend', glyph: '/assets/glyphs/frontend.png' },
    { id: 'backend', label: 'Backend', glyph: '/assets/glyphs/backend.png' },
    { id: 'scroll', label: 'Scroll', glyph: '/assets/glyphs/scroll.png' },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 14 }}>
        <div className="vault-tabs" role="tablist" aria-label="Artifact vault">
          {tabs.map((t) => (
            <button key={t.id} role="tab" aria-selected={tab === t.id} aria-label={t.label} onClick={() => setTab(t.id)} className={`vault-tab ${tab === t.id ? 'active' : ''}`}>
              <img src={t.glyph} alt={t.label + ' icon'} onError={(e) => (e.currentTarget.style.display = 'none')} />
              {t.label}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-ghost" aria-label="Copy wish link" onClick={() => navigator.clipboard.writeText(window.location.href)}>Copy link</button>
          <button className="btn-primary" aria-label="Download runnable zip" onClick={onZip}>Download zip ✦</button>
        </div>
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={tab}
          initial={{ opacity: 0, y: 10, filter: 'blur(4px)' }}
          animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
          exit={{ opacity: 0, y: -8, filter: 'blur(4px)' }}
          transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
        >
          {tab === 'trial' && (
            <Suspense fallback={<div className="glass sandpack-shimmer" style={{ padding: 20, textAlign: 'center', color: 'var(--intara-muted)' }}>Warming up the trial sandbox…</div>}>
              <PreviewTrial artifacts={artifacts} appName={appName} />
            </Suspense>
          )}
          {tab === 'schema' && <SchemaTab artifacts={artifacts} prd={prd} />}
          {tab === 'frontend' && <FrontendTab artifacts={artifacts} />}
          {tab === 'backend' && <BackendTab artifacts={artifacts} />}
          {tab === 'scroll' && <ScrollTab artifacts={artifacts} prd={prd} wish={wish} />}
        </motion.div>
      </AnimatePresence>
    </div>
  )
}

function Code({ title, content, lang }: { title: string; content: string; lang?: string }) {
  return (
    <div style={{ marginBottom: 18 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <span style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)' }}>{title} {lang && <span style={{ fontWeight: 400, textTransform: 'none', opacity: 0.7 }}>· {lang}</span>}</span>
        <button className="btn-ghost" style={{ padding: '6px 12px', fontSize: 11, fontWeight: 450 }} onClick={() => navigator.clipboard.writeText(content)}>Copy</button>
      </div>
      <pre className="code-block" style={{ background: '#08080C', border: '1px solid rgba(255,255,255,0.04)' }}>{content || '// empty'}</pre>
    </div>
  )
}

function SchemaTab({ artifacts, prd }: any) {
  const tables = artifacts.schema?.tables || prd.tables || []
  const prisma = artifacts.schema?.prisma || ''
  const sql = artifacts.schema?.sql || ''
  const json = artifacts.schema ? JSON.stringify({ tables }, null, 2) : JSON.stringify({ tables }, null, 2)
  // Mermaid-ish ER via simple text
  const er = tables.map((t: any) => `${t.name} {\n${(t.fields || []).map((f: any) => `  ${f.type} ${f.name}`).join('\n')}\n}`).join('\n\n')
  return (
    <div>
      <div className="glass" style={{ padding: 14, marginBottom: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--intara-muted)', marginBottom: 8 }}>ER Diagram</div>
        <pre className="code-block" style={{ background: 'rgba(255,255,255,0.04)' }}>{er || '// no tables'}</pre>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
          {tables.map((t: any) => (
            <span key={t.name} style={{ fontSize: 11, border: '1px solid var(--intara-border)', padding: '5px 9px', borderRadius: 999, background: 'rgba(255,255,255,0.06)' }}>
              <b>{t.name}</b> — {(t.fields || []).map((f: any) => `${f.name}:${f.type}`).join(', ')}
            </span>
          ))}
        </div>
      </div>
      <Code title="schema.json" content={json} lang="json" />
      <Code title="schema.prisma" content={prisma} lang="prisma" />
      <Code title="supabase.sql" content={sql} lang="sql" />
    </div>
  )
}

function FrontendTab({ artifacts }: any) {
  const files: { path: string; content: string }[] = artifacts.frontend?.files || []
  const [active, setActive] = useState(0)
  if (!files.length) return <div className="glass" style={{ padding: 20, textAlign: 'center', color: 'var(--intara-muted)' }}>No frontend files — Intara is still weaving.</div>
  return (
    <div className="vault-file-grid" style={{ display: 'grid', gridTemplateColumns: '220px 1fr', gap: 14, alignItems: 'start' }}>
      <div className="glass" style={{ padding: 8 }}>
        <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--intara-muted)', padding: '8px 8px 6px' }}>Files • {files.length}</div>
        {files.map((f, i) => (
          <button key={f.path} onClick={() => setActive(i)} style={{
            width: '100%', textAlign: 'left', padding: '9px 10px', borderRadius: 10, border: '1px solid transparent',
            background: i === active ? 'rgba(255,255,255,0.08)' : 'transparent',
            color: i === active ? 'var(--intara-text)' : 'var(--intara-muted)', fontSize: 12, cursor: 'pointer', fontFamily: 'JetBrains Mono, monospace',
          }}>{f.path}</button>
        ))}
      </div>
      <Code title={files[active].path} content={files[active].content} lang="tsx" />
    </div>
  )
}

function BackendTab({ artifacts }: any) {
  const files: { path: string; content: string }[] = artifacts.backend?.files || []
  const req = artifacts.backend?.requirements || ''
  const openapi = artifacts.backend?.openapi || artifacts.spec?.openapi
  const [active, setActive] = useState(0)
  return (
    <div>
      <div className="vault-file-grid" style={{ display: 'grid', gridTemplateColumns: '220px 1fr', gap: 14, alignItems: 'start', marginBottom: 16 }}>
        <div className="glass" style={{ padding: 8 }}>
          <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--intara-muted)', padding: '8px 8px 6px' }}>Files • {files.length}</div>
          {files.map((f, i) => (
            <button key={f.path} onClick={() => setActive(i)} style={{
              width: '100%', textAlign: 'left', padding: '9px 10px', borderRadius: 10, border: '1px solid transparent',
              background: i === active ? 'rgba(255,255,255,0.08)' : 'transparent',
              color: i === active ? 'var(--intara-text)' : 'var(--intara-muted)', fontSize: 12, cursor: 'pointer', fontFamily: 'JetBrains Mono, monospace',
            }}>{f.path}</button>
          ))}
        </div>
        {files.length ? <Code title={files[active].path} content={files[active].content} lang="py" /> : <div className="glass" style={{ padding: 20, color: 'var(--intara-muted)' }}>No backend files</div>}
      </div>
      <Code title="requirements.txt" content={req} lang="txt" />
      {openapi && <Code title="openapi.json" content={JSON.stringify(openapi, null, 2)} lang="json" />}
    </div>
  )
}

function ScrollTab({ artifacts, prd, wish }: any) {
  const readme = artifacts.spec?.readme || ''
  const cites: string[] = artifacts.spec?.cites || []
  const openapi = artifacts.spec?.openapi || artifacts.backend?.openapi
  return (
    <div>
      <div className="glass" style={{ padding: 16, marginBottom: 16 }}>
        <div style={{ fontFamily: 'Space Grotesk', fontSize: 18, fontWeight: 700 }}>{prd.appName || 'Intara Wish'}</div>
        {prd.tagline && <div style={{ color: 'var(--intara-muted)', fontSize: 13, marginTop: 4 }}>{prd.tagline}</div>}
        <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 11, padding: '5px 9px', borderRadius: 999, background: 'rgba(139,92,246,0.18)', border: '1px solid rgba(139,92,246,0.30)' }}>Wish: {wish.prompt.slice(0, 80)}</span>
          <span style={{ fontSize: 11, padding: '5px 9px', borderRadius: 999, background: 'rgba(255,255,255,0.06)', border: '1px solid var(--intara-border)' }}>{new Date(wish.created_at).toLocaleString()}</span>
        </div>
        {prd.pages && <div style={{ marginTop: 12, display: 'flex', gap: 6, flexWrap: 'wrap' }}>{prd.pages.map((p: any) => <span key={p.route} style={{ fontSize: 11, padding: '4px 8px', borderRadius: 999, border: '1px solid var(--intara-border)', background: 'rgba(255,255,255,0.04)' }}>{p.name} → {p.route}</span>)}</div>}
        {prd.apis && <div style={{ marginTop: 10, display: 'flex', gap: 6, flexWrap: 'wrap' }}>{prd.apis.map((a: any, i: number) => <span key={i} style={{ fontSize: 11, padding: '4px 8px', borderRadius: 999, background: '#0f0f1a', border: '1px solid rgba(255,255,255,0.08)', fontFamily: 'JetBrains Mono, monospace' }}>{a.method} {a.path}</span>)}</div>}
      </div>
      <Code title="README.md" content={readme} lang="markdown" />
      {openapi && <div className="glass" style={{ padding: 14, marginBottom: 16 }}><div style={{ fontSize: 11, fontWeight: 800, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--intara-muted)', marginBottom: 8 }}>APIs (OpenAPI)</div>{Object.entries(openapi.paths || {}).map(([path, methods]: any) => (<div key={path} style={{ fontSize: 12, padding: '8px 10px', borderBottom: '1px solid rgba(255,255,255,0.06)', fontFamily: 'JetBrains Mono, monospace' }}>{path} — {Object.keys(methods).join(', ').toUpperCase()}</div>))}</div>}
      {cites.length > 0 && (
        <div className="glass" style={{ padding: 14 }}>
          <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--intara-muted)', marginBottom: 8 }}>Intara consulted archives — cites</div>
          {cites.map((c, i) => <div key={i} style={{ fontSize: 12, color: 'var(--intara-muted)', padding: '6px 0', borderBottom: i + 1 < cites.length ? '1px solid rgba(255,255,255,0.06)' : 'none' }}>• {c}</div>)}
        </div>
      )}
    </div>
  )
}
