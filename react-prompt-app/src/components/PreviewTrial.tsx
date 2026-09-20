import { SandpackProvider, SandpackPreview, SandpackLayout } from '@codesandbox/sandpack-react'
import { useMemo, useState, useEffect } from 'react'
import { toSandpackFiles } from '../lib/sandpack'

export function PreviewTrial({ artifacts, appName }: { artifacts: any; appName: string }) {
  const files = useMemo(() => toSandpackFiles(artifacts as any), [artifacts])
  const [activeTable, setActiveTable] = useState<string | null>(null)
  const tables: any[] = artifacts.schema?.tables || []

  useEffect(() => {
    if (tables.length && !activeTable) setActiveTable(tables[0].name)
  }, [tables, activeTable])

  if (!artifacts.preview) {
    return <div className="glass" style={{ padding: 20, textAlign: 'center', color: 'var(--intara-muted)', border: '1px dashed var(--intara-border)' }} role="status" aria-live="polite">No preview — regenerate wish for trial. Old wishes from before runnable upgrade lack <code>src/mock/*</code>.</div>
  }

  // custom bundler: Sandpack will auto-install from package.json
  return (
    <div style={{ animation: 'fade-in-fluid 0.5s var(--ease-premium) both' }}>
      <div className="glass" style={{ padding: '12px 14px', marginBottom: 14, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', borderRadius: 14 }}>
        <span style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-nebula-light)', display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--intara-nebula)', boxShadow: '0 0 8px rgba(139,92,246,0.5)', display: 'inline-block' }} />
          Trial — Sandpack instant
        </span>
        <span style={{ fontSize: 11.5, fontWeight: 400, color: 'var(--intara-faint)', letterSpacing: '-0.01em' }}>Browser only · IndexedDB · No Supabase</span>
        <span style={{ marginLeft: 'auto', fontSize: 11, fontWeight: 450, color: 'var(--intara-faint)', border: '1px solid rgba(255,255,255,0.06)', padding: '5px 10px', borderRadius: 999, background: 'rgba(255,255,255,0.02)' }}>{tables.length} tables · 3 seeds · Try Create</span>
      </div>

      <div style={{ border: '1px solid rgba(255,255,255,0.06)', borderRadius: 16, overflow: 'hidden', boxShadow: '0 8px 32px rgba(0,0,0,0.32)' }}>
        <SandpackProvider
          template="react-ts"
          files={files}
          options={{ autorun: true, recompileMode: 'delayed', recompileDelay: 600 }}
          style={{}}
        >
          <SandpackLayout className="sandpack-trial-layout" style={{ border: 'none', flexWrap: 'wrap' }}>
            <div className="sandpack-trial-preview" style={{ flex: 1, minHeight: 380 }}>
              <SandpackPreview
                style={{ height: 380, borderRight: '1px solid var(--intara-border)' }}
                showNavigator={false}
                showOpenInCodeSandbox={false}
                showRefreshButton
              />
            </div>
            <div className="sandpack-trial-sidebar" style={{ width: 300, background: '#0A0A0F', padding: 16, overflow: 'auto', maxHeight: 400 }}>
              <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)', marginBottom: 10 }}>Tables — IndexedDB</div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
                {tables.map((t: any) => (
                  <button
                    key={t.name}
                    onClick={() => setActiveTable(t.name)}
                    style={{
                      padding: '6px 10px', borderRadius: 999, fontSize: 11, fontWeight: activeTable === t.name ? 600 : 450, border: '1px solid ' + (activeTable === t.name ? 'rgba(139,92,246,0.9)' : 'rgba(255,255,255,0.06)'),
                      background: activeTable === t.name ? 'linear-gradient(180deg, #8B5CF6, #7C3AED)' : 'rgba(255,255,255,0.03)',
                      color: activeTable === t.name ? 'white' : 'var(--intara-faint)', cursor: 'pointer', transition: 'all 0.3s var(--ease-premium)'
                    }}
                  >{t.name}</button>
                ))}
              </div>
              <div style={{ fontSize: 11, fontWeight: 400, color: 'var(--intara-faint)', lineHeight: 1.65, letterSpacing: '-0.01em' }}>
                Local to your browser. <span style={{ color: 'var(--intara-muted)', fontWeight: 500 }}>No Supabase needed.</span> Create, refresh — persists in IndexedDB. Connect later via <code style={{ background: 'rgba(255,255,255,0.04)', padding: '1px 5px', borderRadius: 6, fontSize: 10.5 }}>VITE_API_MODE=supabase</code>.
              </div>
              <div style={{ marginTop: 14, padding: '12px 12px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)', borderRadius: 12 }}>
                <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--intara-faint)', marginBottom: 6 }}>How trial works</div>
                <div style={{ fontSize: 11, color: 'var(--intara-dim)', lineHeight: 1.6, fontFamily: 'JetBrains Mono, monospace' }}>
                  <div>· src/mock/db.ts</div>
                  <div>· src/mock/seed.ts</div>
                  <div>· src/mock/server.ts → /api/*</div>
                </div>
              </div>
            </div>
          </SandpackLayout>
        </SandpackProvider>
      </div>

      <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--intara-dim)', letterSpacing: '-0.01em' }}>Tip: Create in preview — Network tab shows no outbound request. Backend <code style={{ background: 'rgba(255,255,255,0.04)', padding: '2px 6px', borderRadius: 6, fontSize: 11, border: '1px solid rgba(255,255,255,0.04)' }}>backend/</code> runs standalone: <code style={{ background: 'rgba(255,255,255,0.04)', padding: '2px 6px', borderRadius: 6, fontSize: 11 }}>pip install -r requirements.txt && uvicorn main:app --port 8000</code></span>
      </div>

      <div className="glass" style={{ marginTop: 12, padding: '12px 14px', display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', borderRadius: 14 }}>
        <span style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)' }}>Connect Supabase</span>
        <code style={{ fontSize: 11, fontWeight: 400, background: '#0A0A0F', padding: '7px 10px', borderRadius: 10, border: '1px solid rgba(255,255,255,0.05)', color: '#CBD5E1', letterSpacing: '-0.01em' }}>VITE_API_MODE=supabase · VITE_SUPABASE_URL · SUPABASE_KEY</code>
        <span style={{ fontSize: 11, color: 'var(--intara-dim)' }}>No regen · env swap only</span>
      </div>
    </div>
  )
}
