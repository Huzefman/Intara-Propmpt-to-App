import { useEffect, useState } from 'react'
import { supabase } from './supabase'
import { generateSchema, askRag } from './api'

// Finished App.tsx — 70 lines you must be able to type in 30 min
// Interview narration: "I debounce the prompt, call a guarded LLM endpoint, then persist to Supabase"

type SchemaRow = { id: string; prompt: string; tables: { name: string; fields: { name: string; type: string }[] }[] }

export default function App() {
  const [prompt, setPrompt] = useState('A task tracker with users, tasks, and due dates')
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [rows, setRows] = useState<SchemaRow[]>([])
  const [q, setQ] = useState('What stack does DhiWise use?')
  const [ragAns, setRagAns] = useState<string>('')

  // load existing schemas
  useEffect(() => {
    supabase.from('schemas').select('*').order('created_at', { ascending: false }).limit(10)
      .then(({ data }) => setRows((data as SchemaRow[]) || []))
  }, [])

  // debounced generate — 350ms
  useEffect(() => {
    if (!prompt.trim()) return
    const id = setTimeout(async () => {
      setLoading(true); setErr(null)
      try {
        const res = await generateSchema(prompt)
        // optimistic insert
        const { data, error } = await supabase.from('schemas').insert({ prompt, tables: res.tables }).select().single()
        if (error) throw error
        setRows(prev => [data as SchemaRow, ...prev].slice(0, 10))
      } catch (e: any) {
        setErr(e.message || 'generate failed')
      } finally {
        setLoading(false)
      }
    }, 350)
    return () => clearTimeout(id)
  }, [prompt])

  async function onAsk() {
    try {
      const res = await askRag(q)
      setRagAns(res.answer + (res.cites.length ? '\n\nCites: ' + res.cites.join(' • ') : ''))
    } catch (e: any) {
      setRagAns('RAG failed: ' + e.message)
    }
  }

  return (
    <div style={{ maxWidth: 860, margin: '0 auto', padding: 24, fontFamily: 'Inter, system-ui, sans-serif' }}>
      <h1 style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-.03em' }}>Prompt → App <span style={{ color: '#6b7280', fontWeight: 400 }}>+ RAG — Finished Demo</span></h1>
      <p style={{ color: '#6b7280', fontSize: 13, marginTop: 6 }}>Type a prompt, debounced → Gemini → Supabase. Second box is RAG over docs.</p>

      <div style={{ marginTop: 18, border: '1px solid #e5e7eb', borderRadius: 12, padding: 14 }}>
        <label style={{ fontSize: 12, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', color: '#6b7280' }}>Prompt</label>
        <textarea value={prompt} onChange={e => setPrompt(e.target.value)} rows={3}
          style={{ width: '100%', marginTop: 8, padding: 10, borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 14 }} />
        {loading && <div style={{ marginTop: 8, fontSize: 12, color: '#6b7280' }}>Generating schema...</div>}
        {err && <div style={{ marginTop: 8, fontSize: 12, color: '#ef4444' }}>{err}</div>}
      </div>

      <div style={{ marginTop: 14, border: '1px solid #e5e7eb', borderRadius: 12, overflow: 'hidden' }}>
        <div style={{ padding: '10px 12px', background: '#f9fafb', borderBottom: '1px solid #e5e7eb', fontSize: 12, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', color: '#6b7280' }}>
          Recent schemas • {rows.length}
        </div>
        <div style={{ maxHeight: 240, overflow: 'auto' }}>
          {rows.map(r => (
            <div key={r.id} style={{ padding: 12, borderBottom: '1px solid #f3f4f6' }}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{r.prompt}</div>
              <div style={{ marginTop: 6, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {r.tables.map(t => (
                  <span key={t.name} style={{ fontSize: 11, border: '1px solid #e5e7eb', padding: '3px 7px', borderRadius: 999, background: 'white' }}>
                    <b>{t.name}</b> — {t.fields.map(f => `${f.name}:${f.type}`).join(', ')}
                  </span>
                ))}
              </div>
            </div>
          ))}
          {!rows.length && <div style={{ padding: 20, textAlign: 'center', color: '#9ca3af', fontSize: 13 }}>No schemas yet. Type a prompt above.</div>}
        </div>
      </div>

      <div style={{ marginTop: 18, border: '1px solid #e5e7eb', borderRadius: 12, padding: 14 }}>
        <label style={{ fontSize: 12, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', color: '#6b7280' }}>RAG — ask docs</label>
        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Ask docs..." style={{ flex: 1, padding: 10, borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 14 }} />
          <button onClick={onAsk} style={{ padding: '10px 14px', borderRadius: 999, border: '1px solid #111827', background: '#111827', color: 'white', fontWeight: 600, cursor: 'pointer' }}>Ask</button>
        </div>
        {ragAns && <pre style={{ marginTop: 10, whiteSpace: 'pre-wrap', fontSize: 13, background: '#f9fafb', padding: 10, borderRadius: 8, border: '1px solid #e5e7eb' }}>{ragAns}</pre>}
      </div>

      <p style={{ marginTop: 14, fontSize: 11, color: '#9ca3af', textAlign: 'center' }}>Finished version — read, then rebuild from <code>demo/starter/</code> empty. 70+65+45 lines.</p>
    </div>
  )
}
