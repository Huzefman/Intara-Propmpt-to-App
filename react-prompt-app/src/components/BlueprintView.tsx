/**
 * BlueprintView (Phase 7, P7.4): the v2 spec as Data / Screens / Rules /
 * Assumptions cards + approve + chat-patch + live RuntimePreview.
 * Driven by a v2 runId: polls status while running, approves versions,
 * sends chat edits (JSON Patch behind a Details toggle).
 */
import { Suspense, lazy, useEffect, useState } from 'react'
import { approveRun, chatRun, getRun, patchRun } from '../api/client'
import { addRole, removeRole, setRule } from '../../../packages/runtime/editing/roles.ts'

const RuntimePreview = lazy(() => import('../runtime/RuntimePreview').then(m => ({ default: m.RuntimePreview })))

function Card({ title, children }: { title: string; children: any }) {
  return (
    <div className="glass" style={{ padding: '12px 14px', borderRadius: 14 }}>
      <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)', marginBottom: 8 }}>{title}</div>
      {children}
    </div>
  )
}

export function BlueprintView({ runId }: { runId: string }) {
  const [run, setRun] = useState<any>(null)
  const [spec, setSpec] = useState<any>(null)
  const [versionId, setVersionId] = useState<string | null>(null)
  const [approved, setApproved] = useState(false)
  const [msg, setMsg] = useState('')
  const [instruction, setInstruction] = useState('')
  const [patch, setPatch] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [newRole, setNewRole] = useState('')

  async function refresh() {
    try {
      const r = await getRun(runId)
      setRun(r.run)
      if (r.spec) { setSpec(r.spec); setVersionId(r.version_id); }
    } catch (e: any) {
      setErr(e.message || 'load failed')
    }
  }

  useEffect(() => {
    refresh()
    const t = setInterval(async () => {
      try {
        const r = await getRun(runId)
        setRun(r.run)
        if (r.spec) { setSpec(r.spec); setVersionId(r.version_id); }
        if (['done', 'degraded', 'failed', 'cancelled'].includes(r.run?.status)) clearInterval(t)
      } catch { /* keep polling */ }
    }, 3000)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId])

  async function approve() {
    setBusy(true); setErr(null)
    try {
      await approveRun(runId)
      setApproved(true)
      setMsg('Approved — this version is the build source of truth.')
    } catch (e: any) {
      setErr(e.message || 'approve failed')
    } finally { setBusy(false) }
  }

  async function applyEdit(edit: { patch: any[]; summary: string }) {
    if (!versionId) { setErr('No version to patch yet.'); return }
    setBusy(true); setErr(null)
    try {
      const r = await patchRun(runId, edit.patch as any[], edit.summary, versionId)
      setSpec(r.spec); setVersionId(r.version_id)
      setMsg(r.summary)
    } catch (e: any) {
      setErr(e.message || 'patch failed')
    } finally { setBusy(false) }
  }

  async function chat() {
    if (instruction.trim().length < 4) return
    setBusy(true); setErr(null); setPatch(null)
    try {
      const r = await chatRun(runId, instruction.trim())
      setSpec(r.spec); setVersionId(r.version_id); setPatch(r)
      setMsg(r.summary || 'Patched.')
      setInstruction('')
    } catch (e: any) {
      setErr(e.message || 'chat patch failed')
    } finally { setBusy(false) }
  }

  const status = run?.status || 'loading'
  const entities = spec?.model?.entities || []
  const pages = spec?.ui?.pages || []
  const rules = spec?.access?.rules || []
  const assumptions = spec?.assumptions || []
  const automations = spec?.automations || []

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div className="glass" style={{ padding: '10px 14px', borderRadius: 14, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-nebula-light)' }}>✦ Blueprint</span>
        <span className={`pill status-${status}`}>{status.replace('_', ' ')}</span>
        {versionId && <span className="mono" style={{ fontSize: 11, color: 'var(--intara-faint)' }}>v{versionId.slice(0, 8)}</span>}
        {approved && <span style={{ fontSize: 11, color: '#6EE7B7' }}>Approved ✓</span>}
        <span style={{ flex: 1 }} />
        <button className="btn-primary btn-sm" onClick={approve} disabled={busy || !versionId || approved}>
          {busy ? 'Working…' : approved ? 'Approved' : 'Approve plan ✦'}
        </button>
      </div>
      {err && <div className="glass" style={{ padding: 10, color: '#FDA4AF', fontSize: 12 }}>{err}</div>}
      {msg && !patch && <div style={{ fontSize: 12, color: 'var(--intara-muted)' }}>{msg}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
        <Card title={`Data · ${entities.length} entities`}>
          {entities.map((e: any) => (
            <div key={e.id} style={{ fontSize: 12, padding: '3px 0' }}>
              <strong>{e.label || e.id}</strong>
              <span style={{ color: 'var(--intara-faint)' }}> · {(e.fields || []).map((f: any) => f.id).join(', ')}</span>
            </div>
          ))}
          {entities.length === 0 && <div className="muted" style={{ fontSize: 12 }}>Model lands when the run reaches S2.</div>}
        </Card>
        <Card title={`Screens · ${pages.length} pages`}>
          {pages.map((p: any) => (
            <div key={p.id} style={{ fontSize: 12, padding: '3px 0' }}>
              <strong>{p.title || p.id}</strong>
              <span style={{ color: 'var(--intara-faint)' }}> · {p.route} · {(p.blocks || []).length} blocks</span>
            </div>
          ))}
          {pages.length === 0 && <div className="muted" style={{ fontSize: 12 }}>Screens land at S3.</div>}
        </Card>
        <Card title={`Rules · ${rules.length} rules · ${automations.length} automations`}>
          {rules.slice(0, 6).map((r: any, i: number) => (
            <div key={i} style={{ fontSize: 12, padding: '3px 0' }}>{r.role} → {r.entity} [{(r.ops || []).join(',')}]</div>
          ))}
          {automations.map((a: any) => (
            <div key={a.id} style={{ fontSize: 12, padding: '3px 0' }}>⚡ {a.id} <span style={{ color: 'var(--intara-faint)' }}>{a.trigger?.type}</span></div>
          ))}
          {rules.length === 0 && <div className="muted" style={{ fontSize: 12 }}>Rules land at S4.</div>}
        </Card>
        <Card title={`Assumptions · ${assumptions.length}`}>
          {assumptions.map((a: any, i: number) => (
            <div key={i} style={{ fontSize: 12, padding: '3px 0' }}>· {String(a)}</div>
          ))}
          {assumptions.length === 0 && <div className="muted" style={{ fontSize: 12 }}>Assumed: nothing yet.</div>}
        </Card>
      </div>

      <div className="glass" style={{ padding: '12px 14px', borderRadius: 14 }}>
        <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)', marginBottom: 8 }}>Roles editor (deterministic patch)</div>
        {(spec?.access?.roles || []).map((r: any) => {
          // quick toggles scope to the primary entity; full-matrix edits go through chat
          const firstEnt = (spec?.model?.entities || [])[0]?.id;
          const rule = (spec?.access?.rules || []).find((x: any) => x.role === r.id && x.entity === firstEnt);
          const on = (op: string) => !!rule && (rule.ops || []).includes(op);
          return (
          <div key={r.id} style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12, padding: '3px 0', flexWrap: 'wrap' }}>
            <strong style={{ minWidth: 90 }}>{r.id}</strong>
            {['read', 'create', 'update', 'delete'].map((op) => (
              <button key={op} className="btn-ghost btn-sm" disabled={busy || !versionId || !firstEnt}
                title={`${on(op) ? 'Remove' : 'Grant'} ${op} for ${r.id} on ${firstEnt}`}
                style={on(op) ? { borderColor: 'rgba(139,92,246,0.9)' } : undefined}
                onClick={() => {
                  try {
                    const cur = (((spec?.access?.rules || []).find((x: any) => x.role === r.id && x.entity === firstEnt)?.ops || []) as string[]);
                    const next = on(op) ? cur.filter((o) => o !== op) : [...cur, op];
                    applyEdit(setRule(spec, r.id, firstEnt, next));
                  } catch (e: any) {
                    setErr(e.message || 'edit failed');
                  }
                }}>
                {op[0].toUpperCase()}
              </button>
            ))}
            <button className="btn-ghost btn-sm" disabled={busy || !versionId}
              onClick={() => {
                try {
                  if (!confirm(`Remove role ${r.id}?`)) return;
                  applyEdit(removeRole(spec, r.id));
                } catch (e: any) {
                  setErr(e.message || 'edit failed');
                }
              }}>✕</button>
          </div>
          );
        })}
        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
          <input
            value={newRole}
            onChange={(e) => setNewRole(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && newRole.trim()) {
                try { applyEdit(addRole(spec, newRole.trim())); setNewRole(''); }
                catch (er: any) { setErr(er.message || 'edit failed'); }
              }
            }}
            placeholder="new-role-id"
            style={{ flex: 1, background: '#0A0A0F', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 10, padding: '8px 12px', color: '#E2E8F0', fontSize: 13 }}
            aria-label="New role id"
          />
          <button className="btn-primary btn-sm" disabled={busy || !versionId || !newRole.trim()}
            onClick={() => {
              try { applyEdit(addRole(spec, newRole.trim())); setNewRole(''); }
              catch (e: any) { setErr(e.message || 'edit failed'); }
            }}>Add role</button>
        </div>
      </div>

      <div className="glass" style={{ padding: '12px 14px', borderRadius: 14 }}>
        <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)', marginBottom: 8 }}>Chat edit (JSON Patch)</div>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') chat() }}
            placeholder='e.g. "add a due date to jobs and show overdue in red"'
            style={{ flex: 1, background: '#0A0A0F', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 10, padding: '8px 12px', color: '#E2E8F0', fontSize: 13 }}
            aria-label="Edit instruction"
          />
          <button className="btn-primary btn-sm" onClick={chat} disabled={busy || !versionId}>Apply</button>
        </div>
        {patch && (
          <div style={{ marginTop: 8, fontSize: 12, color: 'var(--intara-muted)' }}>
            {patch.summary}
            <details style={{ marginTop: 4 }}>
              <summary style={{ cursor: 'pointer', fontSize: 11 }}>Details (JSON Patch)</summary>
              <pre className="mono" style={{ fontSize: 11, overflow: 'auto', background: '#0A0A0F', padding: 8, borderRadius: 8 }}>{JSON.stringify(patch.patch, null, 1)}</pre>
            </details>
          </div>
        )}
      </div>

      {spec && (
        <div className="glass" style={{ padding: '12px 14px', borderRadius: 14 }}>
          <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)', marginBottom: 8 }}>Live preview (no build step)</div>
          <Suspense fallback={<div style={{ padding: 20, textAlign: 'center' }}>Loading app…</div>}>
            <RuntimePreview spec={spec} />
          </Suspense>
        </div>
      )}
    </div>
  )
}
