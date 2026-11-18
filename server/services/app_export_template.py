"""
Export templates for standalone runnable Vite + React + TypeScript apps.
"""

APP_TSX_TEMPLATE = """import React, { useState, useEffect, useMemo } from 'react'
import { db } from './db'
import specData from './spec.json'

export default function App() {
  const spec = specData as any
  const pages = spec?.ui?.pages || []
  const entities = spec?.model?.entities || []
  const appName = spec?.app?.name || 'App'
  const tagline = spec?.app?.tagline || ''

  const [activeRoute, setActiveRoute] = useState<string>(pages[0]?.route || '/')
  const [data, setData] = useState<Record<string, any[]>>({})
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [activeModalEntity, setActiveModalEntity] = useState<any | null>(null)
  const [formData, setFormData] = useState<Record<string, any>>({})

  // Load tables from Dexie IndexedDB
  async function loadAllData() {
    try {
      const out: Record<string, any[]> = {}
      for (const ent of entities) {
        if ((db as any)[ent.id]) {
          out[ent.id] = await (db as any)[ent.id].toArray()
        } else {
          out[ent.id] = []
        }
      }
      setData(out)
    } catch (e) {
      console.error('Failed to load records:', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAllData()
  }, [])

  const currentPage = useMemo(() => {
    return pages.find((p: any) => p.route === activeRoute) || pages[0]
  }, [pages, activeRoute])

  async function handleAddRecord(e: React.FormEvent) {
    e.preventDefault()
    if (!activeModalEntity) return
    const ent = activeModalEntity
    const id = `${ent.id}_${Date.now()}`
    const newRecord = {
      id,
      ...formData,
      created_at: new Date().toISOString(),
    }
    try {
      if ((db as any)[ent.id]) {
        await (db as any)[ent.id].add(newRecord)
      }
      await loadAllData()
      setActiveModalEntity(null)
      setFormData({})
    } catch (err) {
      alert('Could not add record: ' + err)
    }
  }

  async function handleDeleteRecord(entityId: string, id: string) {
    if (!confirm('Are you sure you want to delete this record?')) return
    try {
      if ((db as any)[entityId]) {
        await (db as any)[entityId].delete(id)
        await loadAllData()
      }
    } catch (err) {
      alert('Delete failed: ' + err)
    }
  }

  function exportCsv(entityId: string) {
    const rows = data[entityId] || []
    if (!rows.length) {
      alert('No records to export')
      return
    }
    const headers = Object.keys(rows[0])
    const csvContent = [
      headers.join(','),
      ...rows.map(r => headers.map(h => JSON.stringify(r[h] ?? '')).join(','))
    ].join('\\n')
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${entityId}-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
  }

  return (
    <div className="app-shell">
      {/* Sidebar Navigation */}
      <aside className="app-sidebar">
        <div className="brand">
          <div className="brand-dot" />
          <div>
            <div className="brand-name">{appName}</div>
            {tagline && <div className="brand-tagline">{tagline}</div>}
          </div>
        </div>

        <nav className="nav-links">
          {pages.map((p: any) => (
            <button
              key={p.id}
              className={`nav-item ${p.route === activeRoute ? 'active' : ''}`}
              onClick={() => { setActiveRoute(p.route); setSearchTerm(''); }}
            >
              <span className="nav-bullet">•</span>
              <span>{p.title || p.id}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <span className="badge">Local DB • Offline Ready</span>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="app-main">
        <header className="page-header">
          <div>
            <h1 className="page-title">{currentPage?.title || 'Overview'}</h1>
            <p className="page-subtitle">Route: {currentPage?.route}</p>
          </div>
          <div className="header-actions">
            <button
              className="btn btn-outline btn-sm"
              onClick={() => {
                const ent = entities[0]
                if (ent) {
                  setFormData({})
                  setActiveModalEntity(ent)
                }
              }}
            >
              + Quick Add
            </button>
          </div>
        </header>

        <div className="page-content">
          {loading ? (
            <div className="empty-state">Loading application data…</div>
          ) : (
            (currentPage?.blocks || []).map((b: any) => {
              const entId = b.props?.entity || entities[0]?.id
              const ent = entities.find((e: any) => e.id === entId) || entities[0]
              const rows = data[entId] || []

              // 1. DATA TABLE
              if (b.type === 'data.table') {
                const cols = b.props?.columns || (ent?.fields || []).map((f: any) => f.id)
                const filtered = rows.filter(r => {
                  if (!searchTerm) return true
                  return Object.values(r).some(v => String(v).toLowerCase().includes(searchTerm.toLowerCase()))
                })

                return (
                  <div key={b.id} className="card block-card">
                    <div className="card-header">
                      <div>
                        <h3 className="card-title">{ent?.label || entId} Table</h3>
                        <p className="card-subtitle">{filtered.length} records</p>
                      </div>
                      <div className="card-tools">
                        <input
                          type="text"
                          className="input input-sm"
                          placeholder="Search records…"
                          value={searchTerm}
                          onChange={e => setSearchTerm(e.target.value)}
                        />
                        <button className="btn btn-secondary btn-sm" onClick={() => exportCsv(entId)}>
                          Export CSV
                        </button>
                        <button
                          className="btn btn-primary btn-sm"
                          onClick={() => { setFormData({}); setActiveModalEntity(ent); }}
                        >
                          + Add {ent?.label || 'Record'}
                        </button>
                      </div>
                    </div>

                    <div className="table-responsive">
                      <table className="table">
                        <thead>
                          <tr>
                            {cols.map((c: string) => (
                              <th key={c}>{c.replace(/_/g, ' ')}</th>
                            ))}
                            <th style={{ width: 80 }}>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {filtered.length === 0 ? (
                            <tr>
                              <td colSpan={cols.length + 1} className="empty-cell">
                                No records found. Click "+ Add" to create one.
                              </td>
                            </tr>
                          ) : (
                            filtered.map((r: any) => (
                              <tr key={r.id}>
                                {cols.map((c: string) => (
                                  <td key={c}>
                                    {typeof r[c] === 'boolean' ? (r[c] ? '✓ Yes' : '✗ No') : String(r[c] ?? '-')}
                                  </td>
                                ))}
                                <td>
                                  <button
                                    className="btn-danger-ghost"
                                    onClick={() => handleDeleteRecord(entId, r.id)}
                                  >
                                    Delete
                                  </button>
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )
              }

              // 2. KANBAN
              if (b.type === 'data.kanban') {
                const groupBy = b.props?.group_by || 'status'
                const enumDef = (spec?.model?.enums || []).find((en: any) => en.id === groupBy || en.id.includes(groupBy))
                const stages = enumDef?.values?.map((v: any) => v.value) || ['todo', 'in_progress', 'done']

                return (
                  <div key={b.id} className="card block-card">
                    <div className="card-header">
                      <div>
                        <h3 className="card-title">{ent?.label || entId} Kanban</h3>
                        <p className="card-subtitle">Grouped by {groupBy}</p>
                      </div>
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={() => { setFormData({}); setActiveModalEntity(ent); }}
                      >
                        + Add Card
                      </button>
                    </div>

                    <div className="kanban-board">
                      {stages.map((st: string) => {
                        const inStage = rows.filter((r: any) => (r[groupBy] || '').toLowerCase() === st.toLowerCase())
                        return (
                          <div key={st} className="kanban-col">
                            <div className="kanban-col-header">
                              <span className="col-name">{st.replace(/_/g, ' ')}</span>
                              <span className="col-count">{inStage.length}</span>
                            </div>
                            <div className="kanban-cards">
                              {inStage.map((r: any) => (
                                <div key={r.id} className="kanban-card">
                                  <div className="card-title-sm">{r.title || r.name || r.device || r.id}</div>
                                  <div className="card-meta">
                                    {Object.entries(r)
                                      .filter(([k]) => !['id', 'created_at', groupBy, 'title', 'name'].includes(k))
                                      .slice(0, 2)
                                      .map(([k, v]) => (
                                        <div key={k} className="meta-pill">{k}: {String(v)}</div>
                                      ))}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )
              }

              // 3. STAT METRICS
              if (b.type === 'metric.stat' || b.type === 'metric.gauge') {
                const items = b.props?.items || [
                  { label: 'Total Records', agg: 'count' },
                  { label: 'Active Items', agg: 'count' }
                ]

                return (
                  <div key={b.id} className="metric-grid">
                    {items.map((item: any, idx: number) => {
                      const count = rows.length
                      return (
                        <div key={idx} className="card metric-card">
                          <div className="metric-label">{item.label}</div>
                          <div className="metric-val">{count}</div>
                          <div className="metric-meta">Computed from {ent?.label || entId}</div>
                        </div>
                      )
                    })}
                  </div>
                )
              }

              // Fallback block display
              return (
                <div key={b.id} className="card block-card" style={{ padding: 16 }}>
                  <div style={{ fontWeight: 600, fontSize: 13, color: '#93C5FD' }}>{b.type} block</div>
                  <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 4 }}>
                    Entity: {entId} • {rows.length} records in store
                  </div>
                </div>
              )
            })
          )}
        </div>
      </main>

      {/* Add Record Modal */}
      {activeModalEntity && (
        <div className="modal-backdrop" onClick={() => setActiveModalEntity(null)}>
          <div className="modal-dialog" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Add New {activeModalEntity.label || activeModalEntity.id}</h2>
              <button className="btn-close" onClick={() => setActiveModalEntity(null)}>✕</button>
            </div>
            <form onSubmit={handleAddRecord}>
              <div className="modal-body">
                {(activeModalEntity.fields || []).map((f: any) => {
                  if (f.id === 'id') return null
                  return (
                    <div key={f.id} className="form-group">
                      <label className="form-label">
                        {f.id.replace(/_/g, ' ')} {f.required && <span style={{ color: '#F87171' }}>*</span>}
                      </label>
                      <input
                        type={f.type === 'int' || f.type === 'number' || f.type === 'money' ? 'number' : f.type === 'date' ? 'date' : 'text'}
                        className="input"
                        required={f.required}
                        value={formData[f.id] ?? ''}
                        onChange={e => setFormData({ ...formData, [f.id]: e.target.value })}
                        placeholder={`Enter ${f.id}…`}
                      />
                    </div>
                  )
                })}
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setActiveModalEntity(null)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Save Record
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
"""

INDEX_CSS_TEMPLATE = """:root {
  --bg: #0b0f17;
  --surface: #121824;
  --surface-alt: #1a2233;
  --border: rgba(255, 255, 255, 0.08);
  --border-focus: #3b82f6;
  --text: #f3f4f6;
  --text-dim: #94a3b8;
  --primary: #3b82f6;
  --primary-hover: #2563eb;
  --danger: #ef4444;
  --radius: 12px;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  -webkit-font-smoothing: antialiased;
}

.app-shell {
  display: flex;
  min-height: 100vh;
}

.app-sidebar {
  width: 260px;
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 24px 16px;
  flex-shrink: 0;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 20px;
}

.brand-dot {
  width: 14px;
  height: 14px;
  border-radius: 999px;
  background: linear-gradient(135deg, #60a5fa, #3b82f6);
  box-shadow: 0 0 12px rgba(59, 130, 246, 0.5);
}

.brand-name {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.brand-tagline {
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 2px;
}

.nav-links {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  background: transparent;
  border: none;
  color: var(--text-dim);
  font-size: 13.5px;
  font-weight: 500;
  cursor: pointer;
  text-align: left;
  transition: all 0.15s ease;
}

.nav-item:hover {
  background: rgba(255, 255, 255, 0.04);
  color: var(--text);
}

.nav-item.active {
  background: rgba(59, 130, 246, 0.12);
  color: #93c5fd;
  font-weight: 600;
}

.sidebar-footer {
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.badge {
  font-size: 10.5px;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-dim);
  border: 1px solid var(--border);
}

.app-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px 32px;
  border-bottom: 1px solid var(--border);
  background: rgba(18, 24, 36, 0.5);
  backdrop-filter: blur(8px);
}

.page-title {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 22px;
  font-weight: 700;
}

.page-subtitle {
  font-size: 12px;
  color: var(--text-dim);
  margin-top: 2px;
}

.page-content {
  padding: 32px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.block-card {
  overflow: hidden;
}

.card-header {
  padding: 16px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.01);
}

.card-title {
  font-size: 15px;
  font-weight: 600;
}

.card-subtitle {
  font-size: 11.5px;
  color: var(--text-dim);
  margin-top: 2px;
}

.card-tools {
  display: flex;
  align-items: center;
  gap: 8px;
}

.table-responsive {
  overflow-x: auto;
}

.table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 13px;
}

.table th {
  padding: 12px 18px;
  color: var(--text-dim);
  font-weight: 600;
  text-transform: capitalize;
  border-bottom: 1px solid var(--border);
  font-size: 11.5px;
  letter-spacing: 0.03em;
}

.table td {
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
}

.table tr:last-child td {
  border-bottom: none;
}

.empty-cell {
  text-align: center;
  padding: 40px !important;
  color: var(--text-dim);
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.15s ease;
}

.btn-primary {
  background: var(--primary);
  color: white;
}
.btn-primary:hover {
  background: var(--primary-hover);
}

.btn-secondary {
  background: var(--surface-alt);
  color: var(--text);
  border-color: var(--border);
}
.btn-secondary:hover {
  background: rgba(255, 255, 255, 0.08);
}

.btn-outline {
  background: transparent;
  color: var(--text);
  border-color: var(--border);
}
.btn-outline:hover {
  background: rgba(255, 255, 255, 0.04);
}

.btn-sm {
  padding: 6px 10px;
  font-size: 11.5px;
}

.btn-danger-ghost {
  background: transparent;
  border: none;
  color: var(--danger);
  font-size: 11.5px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
}
.btn-danger-ghost:hover {
  background: rgba(239, 68, 68, 0.1);
}

.input {
  background: var(--surface-alt);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 12.5px;
  outline: none;
}
.input:focus {
  border-color: var(--border-focus);
}
.input-sm {
  padding: 5px 10px;
  font-size: 11.5px;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}

.metric-card {
  padding: 20px;
}

.metric-label {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.metric-val {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 28px;
  font-weight: 700;
  margin: 6px 0 4px;
  color: #60a5fa;
}

.metric-meta {
  font-size: 11px;
  color: var(--text-dim);
}

.kanban-board {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
  padding: 20px;
  background: rgba(0, 0, 0, 0.15);
}

.kanban-col {
  background: var(--surface-alt);
  border-radius: 10px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.kanban-col-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12.5px;
  font-weight: 600;
  text-transform: capitalize;
}

.col-count {
  font-size: 11px;
  background: rgba(255, 255, 255, 0.06);
  padding: 2px 6px;
  border-radius: 999px;
  color: var(--text-dim);
}

.kanban-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.kanban-card {
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 12px;
  border-radius: 8px;
}

.card-title-sm {
  font-size: 13px;
  font-weight: 600;
}

.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.meta-pill {
  font-size: 10.5px;
  background: rgba(255, 255, 255, 0.04);
  padding: 2px 6px;
  border-radius: 4px;
  color: var(--text-dim);
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-dialog {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  width: 100%;
  max-width: 480px;
  overflow: hidden;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 18px 24px;
  border-bottom: 1px solid var(--border);
}

.modal-header h2 {
  font-size: 16px;
  font-weight: 600;
}

.btn-close {
  background: transparent;
  border: none;
  color: var(--text-dim);
  font-size: 16px;
  cursor: pointer;
}

.modal-body {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-height: 60vh;
  overflow-y: auto;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-dim);
  text-transform: capitalize;
}

.modal-footer {
  padding: 16px 24px;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
"""
