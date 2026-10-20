/**
 * VersionTimeline (Phase 9, slice 1): version list with human summaries,
 * parent links, per-version change notes, and one-step undo (revert).
 */
import { useEffect, useState } from 'react'
import { apiFetch } from '../api/client'

export interface VersionInfo {
  id: string
  parent: string | null
  source: string
  summary: string | null
  hash: string
  created_at: string | null
  spec?: any
}

function diffNote(oldSpec: any, newSpec: any): string {
  if (!oldSpec || !newSpec) return ''
  const bits: string[] = []
  const oe = new Set(((oldSpec.model || {}).entities || []).map((e: any) => e.id))
  const ne = new Set(((newSpec.model || {}).entities || []).map((e: any) => e.id))
  const op = new Set(((oldSpec.ui || {}).pages || []).map((p: any) => p.id))
  const np = new Set(((newSpec.ui || {}).pages || []).map((p: any) => p.id))
  for (const e of ne) if (!oe.has(e)) bits.push(`+entity ${e}`)
  for (const e of oe) if (!ne.has(e)) bits.push(`−entity ${e}`)
  for (const p of np) if (!op.has(p)) bits.push(`+page ${p}`)
  for (const p of op) if (!np.has(p)) bits.push(`−page ${p}`)
  return bits.slice(0, 6).join(' · ')
}

export function VersionTimeline({ projectId, onPick }: {
  projectId: string | null
  onPick?: (versionId: string, spec: any) => void
}) {
  const [versions, setVersions] = useState<VersionInfo[]>([])
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function load() {
    if (!projectId) return
    try {
      const res = await apiFetch(`/api/projects/${projectId}/versions`)
      if (!res.ok) throw new Error(`versions failed ${res.status}`)
      const data = await res.json()
      setVersions((data.versions || []).slice().reverse())
    } catch (e: any) {
      setErr(e.message || 'load failed')
    }
  }

  useEffect(() => { load() }, [projectId])

  async function revert(id: string) {
    setBusy(true); setErr(null)
    try {
      const res = await apiFetch(`/api/versions/${id}/revert`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}),
      })
      if (!res.ok) throw new Error(`revert failed ${res.status}`)
      await load()
    } catch (e: any) {
      setErr(e.message || 'revert failed')
    } finally { setBusy(false) }
  }

  if (!projectId) return null
  const byId: Record<string, VersionInfo> = Object.fromEntries(versions.map((v) => [v.id, v]))

  return (
    <div className="glass" style={{ padding: '12px 14px', borderRadius: 14 }}>
      <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)', marginBottom: 8 }}>
        Versions · {versions.length}
      </div>
      {err && <div style={{ color: '#FDA4AF', fontSize: 12, marginBottom: 6 }}>{err}</div>}
      {versions.map((v) => {
        const parent = v.parent ? byId[v.parent] : null
        const note = parent ? diffNote(parent.spec, v.spec) : 'initial version'
        return (
          <div key={v.id} style={{ display: 'flex', gap: 8, alignItems: 'baseline', fontSize: 12, padding: '5px 0', borderTop: '1px solid rgba(255,255,255,0.04)' }}>
            <span className="mono" style={{ color: 'var(--intara-faint)' }}>v{v.id.slice(0, 8)}</span>
            <span style={{ color: 'var(--intara-dim)' }}>{v.source}</span>
            <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {v.summary || <i style={{ color: 'var(--intara-faint)' }}>{note}</i>}
            </span>
            {v.spec && (
              <button className="btn-ghost btn-sm" onClick={() => onPick?.(v.id, v.spec)}>View</button>
            )}
            {v.parent && (
              <button className="btn-ghost btn-sm" disabled={busy} onClick={() => revert(v.id)}>Undo</button>
            )}
          </div>
        );
      })}
      {versions.length === 0 && <div className="muted" style={{ fontSize: 12 }}>No versions yet.</div>}
    </div>
  )
}
