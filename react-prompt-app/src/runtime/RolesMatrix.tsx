/**
 * Roles matrix viewer (Phase 8, slice 4): read-only "who can do what" from
 * the spec's access rules via engine.can — the current role's column is
 * highlighted.
 */
import { useMemo, useState } from 'react'
import type { AppSpec } from '../../../packages/spec/app-spec.ts'
import { can } from '../../../packages/runtime/engine/permissions.ts'

const OPS = ['read', 'create', 'update', 'delete'] as const

function safeCan(spec: AppSpec, role: string, op: string, entity: string): boolean {
  try {
    return Boolean(can(spec, role, op, entity))
  } catch {
    return false
  }
}

export function RolesMatrix({ spec, current }: { spec: AppSpec; current?: string }) {
  const [isOpen, setIsOpen] = useState(true)
  const [filter, setFilter] = useState('')
  const [selectedCell, setSelectedCell] = useState<{ role: string; entity: string } | null>(null)

  const entities = useMemo(() => {
    return (spec?.model?.entities ?? []).map((e) => e.id)
  }, [spec])

  const roles = useMemo(() => {
    return (spec?.access?.roles ?? []).map((r) => r.id)
  }, [spec])

  const filteredEntities = useMemo(() => {
    if (!filter.trim()) return entities
    const term = filter.toLowerCase()
    return entities.filter((e) => e.toLowerCase().includes(term))
  }, [entities, filter])

  if (!roles.length || !entities.length) return null

  return (
    <div className="blk" style={{ marginBottom: 12, borderRadius: 14 }}>
      <div
        onClick={() => setIsOpen((v) => !v)}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          cursor: 'pointer',
          padding: '4px 2px',
          userSelect: 'none',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 11, transition: 'transform 0.2s', transform: isOpen ? 'rotate(90deg)' : 'none', color: 'var(--intara-nebula-light)' }}>
            ▶
          </span>
          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--intara-text)' }}>
            Access Matrix
          </span>
          <span style={{ fontSize: 11, color: 'var(--intara-faint)', background: 'rgba(255,255,255,0.04)', padding: '2px 8px', borderRadius: 999 }}>
            {roles.length} roles × {entities.length} entities
          </span>
        </div>
        <span style={{ fontSize: 11, color: 'var(--intara-faint)' }}>
          {isOpen ? 'Collapse' : 'Expand'}
        </span>
      </div>

      {isOpen && (
        <div style={{ marginTop: 12 }}>
          {/* Controls Bar */}
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 10, flexWrap: 'wrap' }}>
            <input
              type="text"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter entities…"
              className="intara-input"
              style={{ maxWidth: 220, padding: '6px 10px', fontSize: 11.5 }}
            />
            {filter && (
              <button
                type="button"
                onClick={() => setFilter('')}
                className="btn-ghost btn-sm"
                style={{ padding: '4px 8px', fontSize: 11 }}
              >
                Clear
              </button>
            )}
            <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
              <span style={{ fontSize: 10.5, color: 'var(--intara-dim)' }}>Legend:</span>
              <span className="crud-badge crud-badge-create" title="Create">C</span>
              <span className="crud-badge crud-badge-read" title="Read">R</span>
              <span className="crud-badge crud-badge-update" title="Update">U</span>
              <span className="crud-badge crud-badge-delete" title="Delete">D</span>
              <span className="crud-badge crud-badge-all" title="Full CRUD">FULL</span>
            </div>
          </div>

          {/* Matrix Data Table */}
          <div className="blk-table-wrap" style={{ maxHeight: 380, overflowY: 'auto' }}>
            <table className="blk-table">
              <thead>
                <tr>
                  <th style={{ position: 'sticky', top: 0, background: '#0e0e15', zIndex: 2 }}>Entity</th>
                  {roles.map((r) => {
                    const isCur = r === current
                    return (
                      <th
                        key={r}
                        style={{
                          position: 'sticky',
                          top: 0,
                          background: isCur ? 'rgba(139,92,246,0.12)' : '#0e0e15',
                          borderBottom: isCur ? '2px solid var(--intara-nebula)' : undefined,
                          color: isCur ? 'var(--intara-nebula-light)' : undefined,
                          zIndex: 2,
                        }}
                      >
                        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                          <span>{r}</span>
                          {isCur && <span style={{ fontSize: 9.5, fontWeight: 700, padding: '1px 5px', borderRadius: 999, background: 'rgba(139,92,246,0.3)', color: '#fff' }}>Active</span>}
                        </div>
                      </th>
                    )
                  })}
                </tr>
              </thead>
              <tbody>
                {filteredEntities.map((e) => (
                  <tr key={e}>
                    <td style={{ fontWeight: 550, color: 'var(--intara-text)' }}>{e}</td>
                    {roles.map((r) => {
                      const isCur = r === current
                      const allowedOps = OPS.filter((op) => safeCan(spec, r, op, e))
                      const hasAll = allowedOps.length === 4
                      const isSel = selectedCell?.role === r && selectedCell?.entity === e

                      return (
                        <td
                          key={r}
                          onClick={() => setSelectedCell({ role: r, entity: e })}
                          style={{
                            background: isCur ? 'rgba(139,92,246,0.03)' : undefined,
                            cursor: 'pointer',
                            outline: isSel ? '1px solid var(--intara-nebula)' : undefined,
                          }}
                          title={`Click to inspect ${r} on ${e}`}
                        >
                          {allowedOps.length === 0 ? (
                            <span style={{ color: 'var(--intara-dim)', fontSize: 11 }}>—</span>
                          ) : hasAll ? (
                            <span className="crud-badge crud-badge-all">FULL</span>
                          ) : (
                            <div style={{ display: 'inline-flex', gap: 3 }}>
                              {allowedOps.map((op) => (
                                <span
                                  key={op}
                                  className={`crud-badge crud-badge-${op}`}
                                  title={`${op} allowed`}
                                >
                                  {op[0].toUpperCase()}
                                </span>
                              ))}
                            </div>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
                {filteredEntities.length === 0 && (
                  <tr>
                    <td colSpan={roles.length + 1} style={{ textAlign: 'center', padding: 20, color: 'var(--intara-dim)' }}>
                      No matching entities for "{filter}"
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Cell Inspector Drawer / Popover */}
          {selectedCell && (
            <div
              style={{
                marginTop: 10,
                padding: '10px 12px',
                borderRadius: 10,
                background: 'rgba(139,92,246,0.06)',
                border: '1px solid rgba(139,92,246,0.25)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: 8,
              }}
            >
              <div style={{ fontSize: 11.5, color: 'var(--intara-text)' }}>
                <strong>Role:</strong> <span style={{ color: 'var(--intara-nebula-light)' }}>{selectedCell.role}</span>
                <span style={{ margin: '0 8px', opacity: 0.3 }}>·</span>
                <strong>Entity:</strong> <span style={{ color: 'var(--intara-nebula-light)' }}>{selectedCell.entity}</span>
                <span style={{ margin: '0 8px', opacity: 0.3 }}>·</span>
                <strong>Permissions:</strong>{' '}
                {OPS.filter((op) => safeCan(spec, selectedCell.role, op, selectedCell.entity)).join(', ') || 'None'}
              </div>
              <button
                type="button"
                onClick={() => setSelectedCell(null)}
                className="btn-ghost btn-sm"
                style={{ padding: '2px 8px', fontSize: 10.5 }}
              >
                Close ✕
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
