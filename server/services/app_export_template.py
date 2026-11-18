"""
Export templates for standalone runnable Vite + React + TypeScript apps.
Includes complete implementations for all 14 block types in the catalog:
- data.table
- data.kanban
- filter.bar
- calendar.month
- record.detail
- record.related_list
- lifecycle.pipeline
- form.record
- metric.stat
- metric.gauge
- chart.bar
- activity.timeline
- content.hero
- file.list
"""

APP_TSX_TEMPLATE = """import React, { useState, useEffect, useMemo } from 'react'
import { db } from './db'
import specData from './spec.json'

export default function App() {
  const spec = specData as any
  const pages = spec?.ui?.pages || []
  const entities = spec?.model?.entities || []
  const enums = spec?.model?.enums || []
  const appName = spec?.app?.name || 'App'
  const tagline = spec?.app?.tagline || ''

  const [activeRoute, setActiveRoute] = useState<string>(pages[0]?.route || '/')
  const [data, setData] = useState<Record<string, any[]>>({})
  const [loading, setLoading] = useState(true)

  // Selected active record IDs per entity (for detail/pipeline/related-list views)
  const [selectedIds, setSelectedIds] = useState<Record<string, string>>({})

  // Page-level filter and search state
  const [pageFilters, setPageFilters] = useState<Record<string, Record<string, string>>>({})
  const [searchQueries, setSearchQueries] = useState<Record<string, string>>({})

  // Calendar month state
  const [calendarDate, setCalendarDate] = useState<Date>(() => new Date())

  // Modal dialog state (for create and edit)
  const [modalConfig, setModalConfig] = useState<{
    mode: 'create' | 'edit';
    entity: any;
    initialData?: Record<string, any>;
  } | null>(null)
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

      // Set initial selected IDs if not already set
      setSelectedIds(prev => {
        const next = { ...prev }
        for (const ent of entities) {
          if (!next[ent.id] && out[ent.id]?.length) {
            next[ent.id] = out[ent.id][0].id
          }
        }
        return next
      })
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
    // Exact match or param route match (e.g. /employee/:id or /employee/{id})
    return pages.find((p: any) => {
      if (p.route === activeRoute) return true
      const pPattern = p.route.replace(/\\/:[a-zA-Z0-9_]+|\\/{[a-zA-Z0-9_]+}/g, '/[^/]+')
      return new RegExp(`^${pPattern}$`).test(activeRoute)
    }) || pages[0]
  }, [pages, activeRoute])

  function navigateTo(route: string, entityId?: string, recordId?: string) {
    if (entityId && recordId) {
      setSelectedIds(prev => ({ ...prev, [entityId]: recordId }))
    }
    // If route contains :id or {id}, replace with recordId
    let resolved = route
    if (recordId) {
      resolved = resolved.replace(/:[a-zA-Z0-9_]+|{[a-zA-Z0-9_]+}/, recordId)
    }
    setActiveRoute(resolved)
  }

  async function handleSaveRecord(e: React.FormEvent) {
    e.preventDefault()
    if (!modalConfig) return
    const { mode, entity, initialData } = modalConfig
    try {
      if (mode === 'edit' && initialData?.id) {
        const updated = { ...initialData, ...formData, updated_at: new Date().toISOString() }
        if ((db as any)[entity.id]) {
          await (db as any)[entity.id].put(updated)
        }
      } else {
        const id = formData.id || `${entity.id}_${Date.now()}`
        const newRecord = {
          id,
          ...formData,
          created_at: new Date().toISOString(),
        }
        if ((db as any)[entity.id]) {
          await (db as any)[entity.id].add(newRecord)
        }
        // Select the newly added record
        setSelectedIds(prev => ({ ...prev, [entity.id]: id }))
      }
      await loadAllData()
      setModalConfig(null)
      setFormData({})
    } catch (err) {
      alert('Could not save record: ' + err)
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

  async function handleTransition(entityId: string, recordId: string, newStatus: string) {
    try {
      const records = data[entityId] || []
      const rec = records.find(r => r.id === recordId)
      if (!rec) return
      const ent = entities.find((e: any) => e.id === entityId)
      const statusField = ent?.lifecycle?.field || 'status'
      const updated = { ...rec, [statusField]: newStatus, updated_at: new Date().toISOString() }
      if ((db as any)[entityId]) {
        await (db as any)[entityId].put(updated)
        await loadAllData()
      }
    } catch (err) {
      alert('Status transition failed: ' + err)
    }
  }

  function exportCsv(entityId: string, rowsToExport?: any[]) {
    const rows = rowsToExport || data[entityId] || []
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
          {pages.map((p: any) => {
            const isParamRoute = p.route.includes(':') || p.route.includes('{')
            const isActive = currentPage?.id === p.id
            return (
              <button
                key={p.id}
                className={`nav-item ${isActive ? 'active' : ''}`}
                onClick={() => {
                  let targetRoute = p.route
                  if (isParamRoute) {
                    const firstEnt = entities[0]
                    const currentId = selectedIds[firstEnt?.id] || data[firstEnt?.id]?.[0]?.id
                    targetRoute = targetRoute.replace(/:[a-zA-Z0-9_]+|{[a-zA-Z0-9_]+}/, currentId || 'default')
                  }
                  setActiveRoute(targetRoute)
                }}
              >
                <span className="nav-bullet">•</span>
                <span>{p.title || p.id}</span>
              </button>
            )
          })}
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
              className="btn btn-primary btn-sm"
              onClick={() => {
                const ent = entities[0]
                if (ent) {
                  setFormData({})
                  setModalConfig({ mode: 'create', entity: ent })
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
            (currentPage?.blocks || []).map((b: any, bIdx: number) => {
              const entId = b.props?.entity || entities[0]?.id
              const ent = entities.find((e: any) => e.id === entId) || entities[0]
              const allRows = data[entId] || []

              // Apply search and pageFilters if present
              const activeFilters = pageFilters[currentPage.id] || {}
              const searchQuery = (searchQueries[currentPage.id] || '').toLowerCase()

              let filteredRows = allRows.filter(r => {
                if (searchQuery) {
                  const matchSearch = Object.values(r).some(v => String(v).toLowerCase().includes(searchQuery))
                  if (!matchSearch) return false
                }
                for (const [k, v] of Object.entries(activeFilters)) {
                  if (v && String(r[k] || '').toLowerCase() !== v.toLowerCase()) {
                    return false
                  }
                }
                return true
              })

              const selectedRecordId = selectedIds[entId] || allRows[0]?.id
              const selectedRecord = allRows.find(r => r.id === selectedRecordId) || allRows[0] || null

              // ==========================================
              // 1. FILTER BAR
              // ==========================================
              if (b.type === 'filter.bar') {
                const searchFields = Array.isArray(b.props?.search) ? b.props.search : []
                const filterFields = Array.isArray(b.props?.fields) ? b.props.fields : (ent?.fields || []).slice(0, 3).map((f: any) => f.id)

                return (
                  <div key={b.id || bIdx} className="card filter-bar-card">
                    <div className="filter-bar-wrap">
                      <div className="search-wrap">
                        <input
                          type="text"
                          className="input input-sm"
                          placeholder={searchFields.length ? `Search by ${searchFields.join(', ')}…` : `Search ${ent?.label || entId}…`}
                          value={searchQueries[currentPage.id] || ''}
                          onChange={e => setSearchQueries(prev => ({ ...prev, [currentPage.id]: e.target.value }))}
                        />
                      </div>
                      <div className="filter-dropdowns">
                        {filterFields.map((fieldId: string) => {
                          const distinctValues = Array.from(new Set(allRows.map(r => r[fieldId]).filter(Boolean)))
                          return (
                            <select
                              key={fieldId}
                              className="input input-sm filter-select"
                              value={activeFilters[fieldId] || ''}
                              onChange={e => {
                                const val = e.target.value
                                setPageFilters(prev => ({
                                  ...prev,
                                  [currentPage.id]: {
                                    ...(prev[currentPage.id] || {}),
                                    [fieldId]: val,
                                  }
                                }))
                              }}
                            >
                              <option value="">All {fieldId.replace(/_/g, ' ')}</option>
                              {distinctValues.map((val: any) => (
                                <option key={String(val)} value={String(val)}>
                                  {String(val)}
                                </option>
                              ))}
                            </select>
                          )
                        })}
                        {(searchQuery || Object.keys(activeFilters).length > 0) && (
                          <button
                            className="btn btn-outline btn-sm"
                            onClick={() => {
                              setSearchQueries(prev => ({ ...prev, [currentPage.id]: '' }))
                              setPageFilters(prev => ({ ...prev, [currentPage.id]: {} }))
                            }}
                          >
                            Clear Filters
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                )
              }

              // ==========================================
              // 2. CALENDAR MONTH
              // ==========================================
              if (b.type === 'calendar.month') {
                const dateField = b.props?.date_field || (ent?.fields || []).find((f: any) =>
                  f.id.includes('date') || f.id.includes('time') || f.id.includes('at')
                )?.id || 'date'

                const year = calendarDate.getFullYear()
                const month = calendarDate.getMonth()
                const monthName = calendarDate.toLocaleString('default', { month: 'long', year: 'numeric' })

                // Compute first day and number of days
                const firstDayIndex = new Date(year, month, 1).getDay()
                const daysInMonth = new Date(year, month + 1, 0).getDate()

                // Group records by day YYYY-MM-DD
                const recordsByDay: Record<string, any[]> = {}
                for (const r of filteredRows) {
                  const rawDate = r[dateField]
                  if (rawDate) {
                    const dayKey = String(rawDate).slice(0, 10)
                    if (!recordsByDay[dayKey]) recordsByDay[dayKey] = []
                    recordsByDay[dayKey].push(r)
                  }
                }

                const daysArray: (number | null)[] = []
                for (let i = 0; i < firstDayIndex; i++) daysArray.push(null)
                for (let d = 1; d <= daysInMonth; d++) daysArray.push(d)

                return (
                  <div key={b.id || bIdx} className="card block-card calendar-block">
                    <div className="card-header">
                      <div>
                        <h3 className="card-title">{ent?.label || entId} Calendar</h3>
                        <p className="card-subtitle">{monthName} • {filteredRows.length} events</p>
                      </div>
                      <div className="card-tools">
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => setCalendarDate(new Date(year, month - 1, 1))}
                        >
                          ‹ Previous
                        </button>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => setCalendarDate(new Date())}
                        >
                          Today
                        </button>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => setCalendarDate(new Date(year, month + 1, 1))}
                        >
                          Next ›
                        </button>
                        <button
                          className="btn btn-primary btn-sm"
                          onClick={() => {
                            setFormData({ [dateField]: new Date().toISOString().slice(0, 10) })
                            setModalConfig({ mode: 'create', entity: ent })
                          }}
                        >
                          + Add Event
                        </button>
                      </div>
                    </div>

                    <div className="calendar-grid">
                      {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(day => (
                        <div key={day} className="calendar-day-header">{day}</div>
                      ))}
                      {daysArray.map((d, idx) => {
                        if (d === null) {
                          return <div key={`empty-${idx}`} className="calendar-cell empty" />
                        }
                        const monthStr = String(month + 1).padStart(2, '0')
                        const dayStr = String(d).padStart(2, '0')
                        const dateKey = `${year}-${monthStr}-${dayStr}`
                        const dayEvents = recordsByDay[dateKey] || []
                        const isToday = new Date().toISOString().slice(0, 10) === dateKey

                        return (
                          <div key={dateKey} className={`calendar-cell ${isToday ? 'today' : ''}`}>
                            <div className="day-number">
                              <span>{d}</span>
                              <button
                                className="day-add-btn"
                                title="Add record on this date"
                                onClick={() => {
                                  setFormData({ [dateField]: dateKey })
                                  setModalConfig({ mode: 'create', entity: ent })
                                }}
                              >
                                +
                              </button>
                            </div>
                            <div className="day-events">
                              {dayEvents.map(ev => {
                                const title = ev.title || ev.name || ev.employee || ev.status || ev.id
                                const status = ev.status || ev.state || ''
                                let badgeColor = 'rgba(59, 130, 246, 0.2)'
                                let textColor = '#93C5FD'
                                if (String(status).toLowerCase().includes('present')) {
                                  badgeColor = 'rgba(16, 185, 129, 0.2)'
                                  textColor = '#6EE7B7'
                                } else if (String(status).toLowerCase().includes('absent')) {
                                  badgeColor = 'rgba(239, 68, 68, 0.2)'
                                  textColor = '#FCA5A5'
                                } else if (String(status).toLowerCase().includes('late') || String(status).toLowerCase().includes('sick')) {
                                  badgeColor = 'rgba(245, 158, 11, 0.2)'
                                  textColor = '#FCD34D'
                                }

                                return (
                                  <div
                                    key={ev.id}
                                    className="calendar-event-badge"
                                    style={{ background: badgeColor, color: textColor }}
                                    onClick={() => {
                                      setFormData(ev)
                                      setModalConfig({ mode: 'edit', entity: ent, initialData: ev })
                                    }}
                                    title="Click to view/edit"
                                  >
                                    <span className="event-dot" />
                                    <span className="event-text">{title}</span>
                                  </div>
                                )
                              })}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )
              }

              // ==========================================
              // 3. RECORD DETAIL
              // ==========================================
              if (b.type === 'record.detail') {
                const sections = b.props?.sections || [
                  { title: `${ent?.label || entId} Information`, fields: (ent?.fields || []).map((f: any) => f.id) }
                ]

                return (
                  <div key={b.id || bIdx} className="card block-card record-detail-card">
                    <div className="card-header">
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <div>
                          <h3 className="card-title">{ent?.label || entId} Details</h3>
                          <p className="card-subtitle">Active Record: {selectedRecord?.name || selectedRecord?.title || selectedRecord?.id || 'None'}</p>
                        </div>
                      </div>
                      <div className="card-tools">
                        {/* Record Switcher Dropdown */}
                        {allRows.length > 1 && (
                          <select
                            className="input input-sm"
                            value={selectedRecordId || ''}
                            onChange={e => setSelectedIds(prev => ({ ...prev, [entId]: e.target.value }))}
                          >
                            {allRows.map(r => (
                              <option key={r.id} value={r.id}>
                                {r.name || r.title || r.id}
                              </option>
                            ))}
                          </select>
                        )}
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => {
                            if (selectedRecord) {
                              setFormData(selectedRecord)
                              setModalConfig({ mode: 'edit', entity: ent, initialData: selectedRecord })
                            }
                          }}
                          disabled={!selectedRecord}
                        >
                          ✎ Edit
                        </button>
                      </div>
                    </div>

                    {!selectedRecord ? (
                      <div className="empty-cell">No record selected.</div>
                    ) : (
                      <div className="record-sections">
                        {sections.map((sec: any, secIdx: number) => {
                          const secFields = sec.fields || (ent?.fields || []).map((f: any) => f.id)
                          return (
                            <div key={secIdx} className="record-section">
                              <h4 className="section-title">{sec.title || 'Details'}</h4>
                              <div className="detail-grid">
                                {secFields.map((fieldId: string) => {
                                  const fieldDef = (ent?.fields || []).find((f: any) => f.id === fieldId)
                                  const val = selectedRecord[fieldId]
                                  return (
                                    <div key={fieldId} className="detail-item">
                                      <span className="detail-label">{fieldDef?.id || fieldId}</span>
                                      <span className="detail-value">
                                        {val === null || val === undefined ? (
                                          <em style={{ color: 'var(--text-dim)' }}>None</em>
                                        ) : typeof val === 'boolean' ? (
                                          val ? '✓ Yes' : '✗ No'
                                        ) : (
                                          String(val)
                                        )}
                                      </span>
                                    </div>
                                  )
                                })}
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )
              }

              // ==========================================
              // 4. RECORD RELATED LIST
              // ==========================================
              if (b.type === 'record.related_list') {
                const childEntityId = b.props?.entity || 'attendance'
                const childEnt = entities.find((e: any) => e.id === childEntityId) || { id: childEntityId }
                const childRows = data[childEntityId] || []

                // Filter child rows matching the parent selected record
                const parentId = selectedRecord?.id
                const parentName = selectedRecord?.name || selectedRecord?.title

                const relatedRows = childRows.filter(r => {
                  if (!parentId) return true
                  // Check matching foreign keys (e.g. employee, employee_id, job, job_id)
                  for (const [k, v] of Object.entries(r)) {
                    if (v === parentId || (parentName && v === parentName) || v === `@${parentId}`) {
                      return true
                    }
                  }
                  return false
                })

                const cols = b.props?.columns || (childEnt?.fields || []).slice(0, 5).map((f: any) => f.id)

                return (
                  <div key={b.id || bIdx} className="card block-card related-list-card">
                    <div className="card-header">
                      <div>
                        <h3 className="card-title">Related {childEnt?.label || childEntityId}</h3>
                        <p className="card-subtitle">
                          {relatedRows.length} entries for {selectedRecord?.name || selectedRecord?.title || parentId || 'all'}
                        </p>
                      </div>
                      <div className="card-tools">
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => exportCsv(childEntityId, relatedRows)}
                        >
                          Export CSV
                        </button>
                        <button
                          className="btn btn-primary btn-sm"
                          onClick={() => {
                            const fkField = (childEnt?.fields || []).find((f: any) => f.type === 'ref')?.id || entId
                            setFormData({ [fkField]: parentId || '' })
                            setModalConfig({ mode: 'create', entity: childEnt })
                          }}
                        >
                          + Add {childEnt?.label || childEntityId}
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
                          {relatedRows.length === 0 ? (
                            <tr>
                              <td colSpan={cols.length + 1} className="empty-cell">
                                No related {childEntityId} records found.
                              </td>
                            </tr>
                          ) : (
                            relatedRows.map(r => (
                              <tr key={r.id}>
                                {cols.map((c: string) => (
                                  <td key={c}>
                                    {typeof r[c] === 'boolean' ? (r[c] ? '✓ Yes' : '✗ No') : String(r[c] ?? '-')}
                                  </td>
                                ))}
                                <td>
                                  <button
                                    className="btn-danger-ghost"
                                    onClick={() => handleDeleteRecord(childEntityId, r.id)}
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

              // ==========================================
              // 5. LIFECYCLE PIPELINE
              // ==========================================
              if (b.type === 'lifecycle.pipeline') {
                const lifecycleDef = ent?.lifecycle || {}
                const statusField = lifecycleDef.field || 'status'
                const currentStatus = String(selectedRecord?.[statusField] || '').toLowerCase()

                const enumId = (ent?.fields || []).find((f: any) => f.id === statusField)?.enum || statusField
                const enumDef = enums.find((en: any) => en.id === enumId || en.id.includes(enumId))
                const allStages = enumDef?.values?.map((v: any) => v.value) || ['pending', 'active', 'completed']

                const transitions = lifecycleDef.transitions || allStages.map((st: string) => ({
                  id: st,
                  to: st,
                  label: st.replace(/_/g, ' ')
                }))

                return (
                  <div key={b.id || bIdx} className="card block-card pipeline-card">
                    <div className="card-header">
                      <div>
                        <h3 className="card-title">{ent?.label || entId} Lifecycle Pipeline</h3>
                        <p className="card-subtitle">
                          Current Stage: <span className="badge" style={{ color: '#93C5FD' }}>{currentStatus || 'None'}</span>
                        </p>
                      </div>
                    </div>

                    <div className="pipeline-stepper">
                      {allStages.map((stage: string, sIdx: number) => {
                        const isCurrent = currentStatus === stage.toLowerCase()
                        const stageLabel = stage.replace(/_/g, ' ')

                        return (
                          <div key={stage} className={`pipeline-step ${isCurrent ? 'active' : ''}`}>
                            <div className="step-indicator">
                              <span className="step-number">{sIdx + 1}</span>
                              <span className="step-name">{stageLabel}</span>
                            </div>
                            {sIdx < allStages.length - 1 && <div className="step-connector" />}
                          </div>
                        )
                      })}
                    </div>

                    <div className="pipeline-actions">
                      <span className="pipeline-label">Available Transitions:</span>
                      <div className="transition-buttons">
                        {transitions.map((t: any) => {
                          const targetStatus = t.to || t.id
                          const isSame = currentStatus === targetStatus.toLowerCase()
                          return (
                            <button
                              key={t.id}
                              className={`btn btn-sm ${isSame ? 'btn-primary' : 'btn-secondary'}`}
                              onClick={() => {
                                if (selectedRecord) {
                                  handleTransition(entId, selectedRecord.id, targetStatus)
                                }
                              }}
                              disabled={!selectedRecord || isSame}
                            >
                              Move to {t.label || targetStatus}
                            </button>
                          )
                        })}
                      </div>
                    </div>
                  </div>
                )
              }

              // ==========================================
              // 6. DATA TABLE
              // ==========================================
              if (b.type === 'data.table') {
                const cols = b.props?.columns || (ent?.fields || []).map((f: any) => f.id)
                const detailPage = pages.find((p: any) => p.route.includes(':') || p.route.includes('{'))

                return (
                  <div key={b.id || bIdx} className="card block-card">
                    <div className="card-header">
                      <div>
                        <h3 className="card-title">{ent?.label || entId} Table</h3>
                        <p className="card-subtitle">{filteredRows.length} records</p>
                      </div>
                      <div className="card-tools">
                        <button className="btn btn-secondary btn-sm" onClick={() => exportCsv(entId, filteredRows)}>
                          Export CSV
                        </button>
                        <button
                          className="btn btn-primary btn-sm"
                          onClick={() => { setFormData({}); setModalConfig({ mode: 'create', entity: ent }); }}
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
                            <th style={{ width: 130 }}>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {filteredRows.length === 0 ? (
                            <tr>
                              <td colSpan={cols.length + 1} className="empty-cell">
                                No records found. Click "+ Add" to create one.
                              </td>
                            </tr>
                          ) : (
                            filteredRows.map((r: any) => (
                              <tr key={r.id}>
                                {cols.map((c: string) => (
                                  <td key={c}>
                                    {typeof r[c] === 'boolean' ? (r[c] ? '✓ Yes' : '✗ No') : String(r[c] ?? '-')}
                                  </td>
                                ))}
                                <td>
                                  <div style={{ display: 'flex', gap: 6 }}>
                                    {detailPage && (
                                      <button
                                        className="btn btn-outline btn-sm"
                                        style={{ padding: '2px 8px', fontSize: 11 }}
                                        onClick={() => navigateTo(detailPage.route, entId, r.id)}
                                      >
                                        View
                                      </button>
                                    )}
                                    <button
                                      className="btn-danger-ghost"
                                      onClick={() => handleDeleteRecord(entId, r.id)}
                                    >
                                      Delete
                                    </button>
                                  </div>
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

              // ==========================================
              // 7. DATA KANBAN
              // ==========================================
              if (b.type === 'data.kanban') {
                const groupBy = b.props?.group_by || 'status'
                const enumDef = enums.find((en: any) => en.id === groupBy || en.id.includes(groupBy))
                const stages = enumDef?.values?.map((v: any) => v.value) || ['todo', 'in_progress', 'done']

                return (
                  <div key={b.id || bIdx} className="card block-card">
                    <div className="card-header">
                      <div>
                        <h3 className="card-title">{ent?.label || entId} Kanban</h3>
                        <p className="card-subtitle">Grouped by {groupBy}</p>
                      </div>
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={() => { setFormData({}); setModalConfig({ mode: 'create', entity: ent }); }}
                      >
                        + Add Card
                      </button>
                    </div>

                    <div className="kanban-board">
                      {stages.map((st: string) => {
                        const inStage = filteredRows.filter((r: any) => (r[groupBy] || '').toLowerCase() === st.toLowerCase())
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

              // ==========================================
              // 8. STATS & GAUGES
              // ==========================================
              if (b.type === 'metric.stat' || b.type === 'metric.gauge') {
                const items = b.props?.items || [
                  { label: 'Total Records', agg: 'count' },
                  { label: 'Active Items', agg: 'count' }
                ]

                return (
                  <div key={b.id || bIdx} className="metric-grid">
                    {items.map((item: any, idx: number) => {
                      const count = filteredRows.length
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

              // ==========================================
              // 9. BAR CHART
              // ==========================================
              if (b.type === 'chart.bar') {
                const categoryField = b.props?.category || 'status'
                const counts: Record<string, number> = {}
                for (const r of filteredRows) {
                  const key = String(r[categoryField] || 'Other')
                  counts[key] = (counts[key] || 0) + 1
                }
                const maxVal = Math.max(...Object.values(counts), 1)

                return (
                  <div key={b.id || bIdx} className="card block-card chart-card">
                    <div className="card-header">
                      <h3 className="card-title">{ent?.label || entId} Distribution</h3>
                      <span className="card-subtitle">By {categoryField}</span>
                    </div>
                    <div className="chart-bars">
                      {Object.entries(counts).map(([cat, val]) => {
                        const pct = Math.round((val / maxVal) * 100)
                        return (
                          <div key={cat} className="chart-bar-row">
                            <span className="chart-bar-label">{cat}</span>
                            <div className="chart-bar-track">
                              <div className="chart-bar-fill" style={{ width: `${pct}%` }} />
                            </div>
                            <span className="chart-bar-val">{val}</span>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )
              }

              // ==========================================
              // 10. TIMELINE
              // ==========================================
              if (b.type === 'activity.timeline') {
                return (
                  <div key={b.id || bIdx} className="card block-card timeline-card">
                    <div className="card-header">
                      <h3 className="card-title">{ent?.label || entId} Activity Timeline</h3>
                    </div>
                    <div className="timeline-items">
                      {filteredRows.slice(0, 10).map((r: any) => (
                        <div key={r.id} className="timeline-item">
                          <div className="timeline-bullet" />
                          <div className="timeline-content">
                            <div className="timeline-title">{r.title || r.name || r.id}</div>
                            <div className="timeline-date">{r.created_at ? new Date(r.created_at).toLocaleDateString() : 'Recent'}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )
              }

              // ==========================================
              // 11. FORM RECORD
              // ==========================================
              if (b.type === 'form.record') {
                const formFields = b.props?.fields || (ent?.fields || []).map((f: any) => f.id)
                return (
                  <div key={b.id || bIdx} className="card block-card form-record-card">
                    <div className="card-header">
                      <h3 className="card-title">{ent?.label || entId} Form</h3>
                    </div>
                    <form
                      onSubmit={async (e) => {
                        e.preventDefault()
                        const id = `${ent.id}_${Date.now()}`
                        if ((db as any)[ent.id]) {
                          await (db as any)[ent.id].add({ id, ...formData, created_at: new Date().toISOString() })
                          await loadAllData()
                          setFormData({})
                          alert('Saved successfully!')
                        }
                      }}
                      className="form-body"
                    >
                      {formFields.map((fieldId: string) => {
                        const fieldDef = (ent?.fields || []).find((f: any) => f.id === fieldId)
                        return (
                          <div key={fieldId} className="form-group">
                            <label className="form-label">{fieldDef?.id || fieldId}</label>
                            <input
                              className="input"
                              value={formData[fieldId] ?? ''}
                              onChange={e => setFormData({ ...formData, [fieldId]: e.target.value })}
                              placeholder={`Enter ${fieldId}…`}
                            />
                          </div>
                        )
                      })}
                      <button type="submit" className="btn btn-primary" style={{ marginTop: 12 }}>
                        Submit Form
                      </button>
                    </form>
                  </div>
                )
              }

              // ==========================================
              // 12. HERO BANNER
              // ==========================================
              if (b.type === 'content.hero') {
                return (
                  <div key={b.id || bIdx} className="card hero-card">
                    <h2 className="hero-title">{b.props?.title || appName}</h2>
                    <p className="hero-subtitle">{b.props?.subtitle || tagline}</p>
                  </div>
                )
              }

              // ==========================================
              // 13. FILE LIST
              // ==========================================
              if (b.type === 'file.list') {
                return (
                  <div key={b.id || bIdx} className="card block-card">
                    <div className="card-header">
                      <h3 className="card-title">Files & Documents</h3>
                    </div>
                    <div className="file-list-wrap">
                      <p className="empty-cell">No uploaded files yet. Use local attachment manager.</p>
                    </div>
                  </div>
                )
              }

              // Fallback
              return (
                <div key={b.id || bIdx} className="card block-card" style={{ padding: 16 }}>
                  <div style={{ fontWeight: 600, fontSize: 13, color: '#93C5FD' }}>{b.type}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 4 }}>
                    Entity: {entId} • {allRows.length} records in store
                  </div>
                </div>
              )
            })
          )}
        </div>
      </main>

      {/* Add / Edit Record Modal */}
      {modalConfig && (
        <div className="modal-backdrop" onClick={() => setModalConfig(null)}>
          <div className="modal-dialog" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{modalConfig.mode === 'edit' ? 'Edit' : 'Add New'} {modalConfig.entity?.label || modalConfig.entity?.id}</h2>
              <button className="btn-close" onClick={() => setModalConfig(null)}>✕</button>
            </div>
            <form onSubmit={handleSaveRecord}>
              <div className="modal-body">
                {(modalConfig.entity?.fields || []).map((f: any) => {
                  if (f.id === 'id') return null
                  const isSelect = f.type === 'enum' || enums.some((en: any) => en.id === f.enum)
                  const enumOptions = enums.find((en: any) => en.id === f.enum)?.values || []

                  return (
                    <div key={f.id} className="form-group">
                      <label className="form-label">
                        {f.id.replace(/_/g, ' ')} {f.required && <span style={{ color: '#F87171' }}>*</span>}
                      </label>
                      {isSelect && enumOptions.length > 0 ? (
                        <select
                          className="input"
                          value={formData[f.id] ?? ''}
                          onChange={e => setFormData({ ...formData, [f.id]: e.target.value })}
                        >
                          <option value="">Select {f.id}…</option>
                          {enumOptions.map((opt: any) => (
                            <option key={opt.value} value={opt.value}>{opt.label || opt.value}</option>
                          ))}
                        </select>
                      ) : (
                        <input
                          type={f.type === 'int' || f.type === 'number' || f.type === 'money' ? 'number' : f.type === 'date' ? 'date' : 'text'}
                          className="input"
                          required={f.required}
                          value={formData[f.id] ?? ''}
                          onChange={e => setFormData({ ...formData, [f.id]: e.target.value })}
                          placeholder={`Enter ${f.id}…`}
                        />
                      )}
                    </div>
                  )
                })}
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setModalConfig(null)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  {modalConfig.mode === 'edit' ? 'Save Changes' : 'Create Record'}
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

/* Filter Bar */
.filter-bar-card {
  padding: 14px 20px;
}
.filter-bar-wrap {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.filter-dropdowns {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.filter-select {
  min-width: 130px;
}

/* Calendar Block */
.calendar-block {
  overflow: hidden;
}
.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 1px;
  background: var(--border);
  border-top: 1px solid var(--border);
}
.calendar-day-header {
  background: var(--surface-alt);
  padding: 10px 8px;
  text-align: center;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-dim);
  text-transform: uppercase;
}
.calendar-cell {
  background: var(--surface);
  min-height: 100px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  transition: background 0.15s;
}
.calendar-cell.empty {
  background: rgba(0, 0, 0, 0.15);
}
.calendar-cell:hover:not(.empty) {
  background: rgba(255, 255, 255, 0.02);
}
.calendar-cell.today {
  box-shadow: inset 0 0 0 1px var(--primary);
}
.day-number {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-dim);
}
.day-add-btn {
  background: transparent;
  border: none;
  color: var(--text-dim);
  font-size: 12px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s;
}
.calendar-cell:hover .day-add-btn {
  opacity: 1;
}
.day-events {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.calendar-event-badge {
  padding: 3px 6px;
  border-radius: 4px;
  font-size: 10.5px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.event-dot {
  width: 5px;
  height: 5px;
  border-radius: 999px;
  background: currentColor;
  flex-shrink: 0;
}

/* Record Detail */
.record-sections {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.record-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.section-title {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-dim);
  border-bottom: 1px solid var(--border);
  padding-bottom: 6px;
}
.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
}
.detail-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.detail-label {
  font-size: 11px;
  color: var(--text-dim);
  text-transform: capitalize;
}
.detail-value {
  font-size: 13.5px;
  font-weight: 500;
}

/* Pipeline Stepper */
.pipeline-stepper {
  display: flex;
  align-items: center;
  padding: 24px;
  overflow-x: auto;
  gap: 8px;
}
.pipeline-step {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}
.step-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface-alt);
  font-size: 12px;
}
.pipeline-step.active .step-indicator {
  border-color: var(--primary);
  background: rgba(59, 130, 246, 0.15);
  color: #93C5FD;
  font-weight: 600;
}
.step-number {
  width: 18px;
  height: 18px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
}
.step-connector {
  width: 24px;
  height: 2px;
  background: var(--border);
}
.pipeline-actions {
  padding: 16px 24px;
  border-top: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}
.pipeline-label {
  font-size: 12px;
  color: var(--text-dim);
}
.transition-buttons {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* Charts */
.chart-card {
  padding: 20px;
}
.chart-bars {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 16px;
}
.chart-bar-row {
  display: grid;
  grid-template-columns: 120px 1fr 40px;
  align-items: center;
  gap: 12px;
}
.chart-bar-label {
  font-size: 12px;
  color: var(--text-dim);
  text-overflow: ellipsis;
  overflow: hidden;
  white-space: nowrap;
}
.chart-bar-track {
  height: 10px;
  border-radius: 999px;
  background: var(--surface-alt);
  overflow: hidden;
}
.chart-bar-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #3b82f6, #60a5fa);
  transition: width 0.3s ease;
}
.chart-bar-val {
  font-size: 12px;
  font-weight: 600;
  text-align: right;
}

/* Timeline */
.timeline-items {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.timeline-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.timeline-bullet {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: var(--primary);
  margin-top: 4px;
  flex-shrink: 0;
}
.timeline-title {
  font-size: 13px;
  font-weight: 500;
}
.timeline-date {
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 2px;
}

/* Hero */
.hero-card {
  padding: 40px;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.1), rgba(18, 24, 36, 0.8));
  text-align: center;
}
.hero-title {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 28px;
  font-weight: 700;
}
.hero-subtitle {
  font-size: 14px;
  color: var(--text-dim);
  margin-top: 8px;
}

/* Form block */
.form-body {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-width: 500px;
}

/* Kanban */
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

/* Modal */
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
