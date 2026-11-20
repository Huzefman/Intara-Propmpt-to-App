import { SandpackProvider, SandpackPreview, SandpackLayout } from '@codesandbox/sandpack-react'
import { useMemo, useState, useEffect } from 'react'
import { toSandpackFiles } from '../lib/sandpack'

export function PreviewTrial({ artifacts, appName }: { artifacts: any; appName: string }) {
  const artifactsJson = useMemo(() => JSON.stringify(artifacts), [artifacts])
  const files = useMemo(() => toSandpackFiles(artifacts as any), [artifactsJson])
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
      <div className="glass" style={{ padding: '14px 18px', marginBottom: 14, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', borderRadius: 16 }}>
        <span style={{ fontSize: 13, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-nebula-light)', display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--intara-nebula)', boxShadow: '0 0 8px rgba(139,92,246,0.6)', display: 'inline-block' }} />
          Interactive Live Preview
        </span>
        <span style={{ fontSize: 13, fontWeight: 400, color: 'var(--intara-faint)', letterSpacing: '-0.01em' }}>Fully functional in-browser app demo with local data</span>
        <span style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 500, color: 'var(--intara-muted)', border: '1px solid rgba(255,255,255,0.08)', padding: '5px 12px', borderRadius: 999, background: 'rgba(255,255,255,0.03)' }}>{tables.length} data tables · Sample records ready</span>
      </div>

      <div style={{ border: '1px solid rgba(255,255,255,0.08)', borderRadius: 16, overflow: 'hidden', boxSizing: 'border-box', boxShadow: '0 8px 32px rgba(0,0,0,0.32)' }}>
        <SandpackProvider
          template="react-ts"
          files={files}
          options={{ autorun: true, recompileMode: 'delayed', recompileDelay: 600 }}
          style={{}}
        >
          <SandpackLayout className="sandpack-trial-layout" style={{ border: 'none', flexWrap: 'wrap' }}>
            <div className="sandpack-trial-preview" style={{ flex: 1, minHeight: 420 }}>
              <SandpackPreview
                style={{ height: 420, borderRight: '1px solid var(--intara-border)' }}
                showNavigator={false}
                showOpenInCodeSandbox={false}
                showRefreshButton
              />
            </div>
            <div className="sandpack-trial-sidebar" style={{ width: 320, background: '#0A0A0F', padding: 18, overflow: 'auto', maxHeight: 440 }}>
              <div style={{ fontSize: 12.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)', marginBottom: 12 }}>Data Tables</div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
                {tables.map((t: any) => (
                  <button
                    key={t.name}
                    onClick={() => setActiveTable(t.name)}
                    style={{
                      padding: '7px 12px', borderRadius: 999, fontSize: 12.5, fontWeight: activeTable === t.name ? 600 : 450, border: '1px solid ' + (activeTable === t.name ? 'rgba(139,92,246,0.9)' : 'rgba(255,255,255,0.08)'),
                      background: activeTable === t.name ? 'linear-gradient(180deg, #8B5CF6, #7C3AED)' : 'rgba(255,255,255,0.03)',
                      color: activeTable === t.name ? 'white' : 'var(--intara-faint)', cursor: 'pointer', transition: 'all 0.3s var(--ease-premium)'
                    }}
                  >{t.name}</button>
                ))}
              </div>
              <div style={{ fontSize: 13, fontWeight: 400, color: 'var(--intara-faint)', lineHeight: 1.65, letterSpacing: '-0.01em' }}>
                Local to your browser. <span style={{ color: 'var(--intara-muted)', fontWeight: 500 }}>All records you create stay saved</span> directly in your browser session with instant data persistence.
              </div>
              <div style={{ marginTop: 16, padding: '14px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 12 }}>
                <div style={{ fontSize: 12, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--intara-faint)', marginBottom: 8 }}>Included Features</div>
                <div style={{ fontSize: 12.5, color: 'var(--intara-muted)', lineHeight: 1.7 }}>
                  <div>✦ Interactive Data Records</div>
                  <div>✦ Automatic Input Validation</div>
                  <div>✦ Responsive Mobile &amp; Desktop Views</div>
                </div>
              </div>
            </div>
          </SandpackLayout>
        </SandpackProvider>
      </div>

      <div style={{ marginTop: 14, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ fontSize: 13, fontWeight: 400, color: 'var(--intara-faint)', letterSpacing: '-0.01em' }}>Tip: Create or edit records in the preview to explore your application. Everything updates in real time.</span>
      </div>

      <div className="glass" style={{ marginTop: 14, padding: '14px 18px', display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', borderRadius: 16 }}>
        <span style={{ fontSize: 12, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-nebula-light)' }}>Deployment Ready</span>
        <span style={{ fontSize: 13, color: 'var(--intara-text)' }}>Export as a standalone project or connect to any cloud database anytime.</span>
      </div>
    </div>
  )
}
