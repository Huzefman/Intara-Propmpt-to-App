/**
 * VersionTimeline (Phase 9, slice 1): version list with human summaries,
 * parent links, per-version change notes, and safe two-step rollback.
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

interface SpecDiff {
  addedEntities: string[]
  removedEntities: string[]
  addedPages: string[]
  removedPages: string[]
}

function computeDiff(oldSpec: any, newSpec: any): SpecDiff {
  if (!oldSpec || !newSpec) {
    return { addedEntities: [], removedEntities: [], addedPages: [], removedPages: [] }
  }
  const oe = new Set(((oldSpec.model || {}).entities || []).map((e: any) => e.id))
  const ne = new Set(((newSpec.model || {}).entities || []).map((e: any) => e.id))
  const op = new Set(((oldSpec.ui || {}).pages || []).map((p: any) => p.id))
  const np = new Set(((newSpec.ui || {}).pages || []).map((p: any) => p.id))

  const addedEntities: string[] = []
  const removedEntities: string[] = []
  const addedPages: string[] = []
  const removedPages: string[] = []

  for (const e of ne) if (!oe.has(e)) addedEntities.push(String(e))
  for (const e of oe) if (!ne.has(e)) removedEntities.push(String(e))
  for (const p of np) if (!op.has(p)) addedPages.push(String(p))
  for (const p of op) if (!np.has(p)) removedPages.push(String(p))

  return { addedEntities, removedEntities, addedPages, removedPages }
}

export function VersionTimeline({ projectId, onPick }: {
  projectId: string | null
  onPick?: (versionId: string, spec: any) => void
}) {
  const [versions, setVersions] = useState<VersionInfo[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [err, setErr] = useState<string | null>(null)
  const [revertingId, setRevertingId] = useState<string | null>(null)
  const [confirmRevertId, setConfirmRevertId] = useState<string | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)

  async function load() {
    if (!projectId) return
    setLoading(true)
    setErr(null)
    try {
      const res = await apiFetch(`/api/projects/${projectId}/versions`)
      if (!res.ok) throw new Error(`versions failed ${res.status}`)
      const data = await res.json()
      setVersions((data.versions || []).slice().reverse())
    } catch (e: any) {
      setErr(e.message || 'load failed')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [projectId])

  async function revert(id: string) {
    setRevertingId(id)
    setErr(null)
    try {
      const res = await apiFetch(`/api/versions/${id}/revert`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      if (!res.ok) throw new Error(`revert failed ${res.status}`)
      setConfirmRevertId(null)
      await load()
    } catch (e: any) {
      setErr(e.message || 'revert failed')
    } finally {
      setRevertingId(null)
    }
  }

  function copyHash(id: string) {
    try {
      navigator.clipboard.writeText(id)
      setCopiedId(id)
      setTimeout(() => setCopiedId(null), 1600)
    } catch {}
  }

  if (!projectId) return null
  const byId: Record<string, VersionInfo> = Object.fromEntries(versions.map((v) => [v.id, v]))

  return (
    <div className="glass" style={{ padding: '16px 18px', borderRadius: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-nebula-light)' }}>
            ✦ Version History
          </span>
          <span style={{ fontSize: 10.5, padding: '2px 8px', borderRadius: 999, background: 'rgba(255,255,255,0.05)', color: 'var(--intara-muted)' }}>
            {versions.length} checkpoints
          </span>
        </div>
        <button
          type="button"
          onClick={() => load()}
          disabled={loading}
          className="btn-ghost btn-sm"
          style={{ padding: '3px 8px', fontSize: 11 }}
          title="Refresh version history"
        >
          {loading ? 'Refreshing…' : '↻ Refresh'}
        </button>
      </div>

      {err && (
        <div
          role="alert"
          style={{
            padding: '8px 12px',
            borderRadius: 10,
            background: 'rgba(248,113,113,0.08)',
            border: '1px solid rgba(248,113,113,0.25)',
            color: '#FDA4AF',
            fontSize: 12,
            marginBottom: 10,
          }}
        >
          {err}
        </div>
      )}

      {loading && versions.length === 0 ? (
        <div style={{ display: 'grid', gap: 10, padding: '8px 0' }}>
          {[1, 2, 3].map((n) => (
            <div key={n} className="skeleton" style={{ height: 48, width: '100%' }} />
          ))}
        </div>
      ) : versions.length === 0 ? (
        <div style={{ color: 'var(--intara-dim)', fontSize: 12, padding: '12px 0', textAlign: 'center' }}>
          No version checkpoints yet. Edits made in the Studio create checkpoints automatically.
        </div>
      ) : (
        <div className="v-timeline">
          <div className="v-timeline-line" />
          {versions.map((v, idx) => {
            const parent = v.parent ? byId[v.parent] : null
            const diff = parent ? computeDiff(parent.spec, v.spec) : null
            const isInitial = idx === versions.length - 1
            const isReverting = revertingId === v.id
            const isConfirming = confirmRevertId === v.id

            return (
              <div key={v.id} className={`v-timeline-item ${idx === 0 ? 'active' : ''}`}>
                <span className="v-timeline-node" />
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      onClick={() => copyHash(v.id)}
                      className="mono"
                      title="Click to copy full ID"
                      style={{
                        background: 'rgba(255,255,255,0.04)',
                        border: '1px solid rgba(255,255,255,0.08)',
                        borderRadius: 6,
                        padding: '2px 6px',
                        fontSize: 11,
                        color: copiedId === v.id ? '#34D399' : 'var(--intara-text)',
                        cursor: 'pointer',
                      }}
                    >
                      {copiedId === v.id ? '✓ copied' : `v${v.id.slice(0, 8)}`}
                    </button>
                    <span style={{ fontSize: 11, color: 'var(--intara-dim)' }}>
                      via {v.source || 'studio'}
                    </span>
                    {idx === 0 && (
                      <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--intara-nebula-light)', background: 'rgba(139,92,246,0.15)', border: '1px solid rgba(139,92,246,0.35)', padding: '1px 6px', borderRadius: 999 }}>
                        Current Head
                      </span>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    {v.spec && (
                      <button
                        type="button"
                        className="btn-ghost btn-sm"
                        style={{ padding: '3px 9px', fontSize: 11 }}
                        onClick={() => onPick?.(v.id, v.spec)}
                      >
                        Inspect
                      </button>
                    )}
                    {v.parent && !isConfirming && (
                      <button
                        type="button"
                        className="btn-ghost btn-sm"
                        style={{ padding: '3px 9px', fontSize: 11, color: '#FCA5A5' }}
                        disabled={Boolean(revertingId)}
                        onClick={() => setConfirmRevertId(v.id)}
                      >
                        Undo
                      </button>
                    )}
                  </div>
                </div>

                {/* Change note or diff pills */}
                <div style={{ fontSize: 12, color: 'var(--intara-muted)', marginTop: 2 }}>
                  {v.summary ? (
                    <span>{v.summary}</span>
                  ) : isInitial ? (
                    <span style={{ color: 'var(--intara-faint)', fontStyle: 'italic' }}>Initial baseline project spec</span>
                  ) : (
                    <span style={{ color: 'var(--intara-faint)' }}>Checkpoint update</span>
                  )}
                </div>

                {/* Diff Micro-badges */}
                {diff && (
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
                    {diff.addedEntities.map((e) => (
                      <span key={`+e-${e}`} className="diff-badge-add">+{e}</span>
                    ))}
                    {diff.removedEntities.map((e) => (
                      <span key={`-e-${e}`} className="diff-badge-remove">−{e}</span>
                    ))}
                    {diff.addedPages.map((p) => (
                      <span key={`+p-${p}`} className="diff-badge-add">+page {p}</span>
                    ))}
                    {diff.removedPages.map((p) => (
                      <span key={`-p-${p}`} className="diff-badge-remove">−page {p}</span>
                    ))}
                  </div>
                )}

                {/* Safe Two-Step Rollback Popover */}
                {isConfirming && (
                  <div
                    style={{
                      marginTop: 8,
                      padding: '8px 12px',
                      borderRadius: 10,
                      background: 'rgba(239,68,68,0.08)',
                      border: '1px solid rgba(239,68,68,0.3)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      flexWrap: 'wrap',
                      gap: 8,
                    }}
                  >
                    <span style={{ fontSize: 11.5, color: '#FCA5A5' }}>
                      Revert current build state back to <strong>v{v.id.slice(0, 8)}</strong>?
                    </span>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button
                        type="button"
                        onClick={() => revert(v.id)}
                        disabled={isReverting}
                        className="btn-primary btn-sm"
                        style={{
                          padding: '3px 10px',
                          fontSize: 11,
                          background: 'linear-gradient(180deg, #EF4444 0%, #DC2626 100%)',
                          borderColor: '#F87171',
                        }}
                      >
                        {isReverting ? 'Reverting…' : 'Confirm Revert'}
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirmRevertId(null)}
                        disabled={isReverting}
                        className="btn-ghost btn-sm"
                        style={{ padding: '3px 8px', fontSize: 11 }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
