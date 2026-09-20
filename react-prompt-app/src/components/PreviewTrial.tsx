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
    return <div className="glass" style={{ padding: 20, textAlign: 'center', color: 'var(--intara-muted)' }}>No preview — regenerate wish for trial</div>
  }

  // custom bundler: Sandpack will auto-install from package.json
  return (
    <div>
      <div className="glass" style={{ padding: 12, marginBottom: 12, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: '.08em', textTransform: 'uppercase', color: '#8B5CF6' }}>● Trial — Sandpack instant</span>
        <span style={{ fontSize: 11, color: 'var(--intara-muted)' }}>Runs entirely in your browser • IndexedDB relational • No Supabase needed</span>
        <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--intara-faint)', border: '1px solid var(--intara-border)', padding: '4px 8px', borderRadius: 999 }}>Mock DB: {tables.length} tables • Seed 3 rows each • Try Create</span>
      </div>

      <div style={{ border: '1px solid var(--intara-border)', borderRadius: 12, overflow: 'hidden' }}>
        <SandpackProvider
          template="react-ts"
          files={files}
          options={{ autorun: true, recompileMode: 'delayed', recompileDelay: 600 }}
          style={{}}
        >
          <SandpackLayout style={{ border: 'none' }}>
            <div style={{ flex: 1, minHeight: 380 }}>
              <SandpackPreview
                style={{ height: 380, borderRight: '1px solid var(--intara-border)' }}
                showNavigator={false}
                showOpenInCodeSandbox={false}
                showRefreshButton
              />
            </div>
            <div style={{ width: 280, background: '#0f0f1a', padding: 12, overflow: 'auto', maxHeight: 380 }}>
              <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--intara-muted)', marginBottom: 8 }}>Tables (IndexedDB)</div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
                {tables.map((t: any) => (
                  <button
                    key={t.name}
                    onClick={() => setActiveTable(t.name)}
                    style={{
                      padding: '5px 9px', borderRadius: 999, fontSize: 11, border: '1px solid var(--intara-border)',
                      background: activeTable === t.name ? '#8B5CF6' : 'rgba(255,255,255,0.06)',
                      color: activeTable === t.name ? 'white' : 'var(--intara-muted)', cursor: 'pointer'
                    }}
                  >{t.name}</button>
                ))}
              </div>
              <div style={{ fontSize: 11, color: 'var(--intara-faint)', lineHeight: 1.6 }}>
                Preview DB is local to your browser. <b>Supabase not required.</b> Create items in the preview, refresh — they persist in IndexedDB. Connect Supabase later: set `VITE_API_MODE=supabase` + `VITE_SUPABASE_URL` and point `VITE_API_URL` to your backend.
              </div>
              <div style={{ marginTop: 12, fontSize: 11, color: 'var(--intara-muted)' }}>
                <div style={{ fontWeight: 700, marginBottom: 4 }}>How trial works</div>
                <div>• `src/mock/db.ts` Dexie stores per table</div>
                <div>• `src/mock/seed.ts` 3 rows</div>
                <div>• `src/mock/server.ts` intercepts `/api/*` → Dexie</div>
              </div>
            </div>
          </SandpackLayout>
        </SandpackProvider>
      </div>

      <div style={{ marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 11, color: 'var(--intara-faint)' }}>Tip: Click Create in preview, then check Network tab — no request leaves browser. Backend `backend/` still runs standalone with SQLite: <code style={{ background: 'rgba(255,255,255,0.06)', padding: '2px 6px', borderRadius: 6 }}>pip install -r requirements.txt && uvicorn main:app --port 8000</code></span>
      </div>

      <div className="glass" style={{ marginTop: 12, padding: 10, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--intara-muted)' }}>Connect Supabase</span>
        <code style={{ fontSize: 11, background: '#0f0f1a', padding: '6px 8px', borderRadius: 8, border: '1px solid var(--intara-border)', color: '#e2e8f0' }}>VITE_API_MODE=supabase VITE_SUPABASE_URL=https://... SUPABASE_URL=... SUPABASE_KEY=...</code>
        <span style={{ fontSize: 11, color: 'var(--intara-faint)' }}>No regen needed — just env swap</span>
      </div>
    </div>
  )
}
