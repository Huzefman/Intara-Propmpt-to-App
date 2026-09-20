import { useState } from 'react'
import { askRag } from '../api/client'

export function Archives() {
  const [q, setQ] = useState('What is Intara?')
  const [ans, setAns] = useState('')
  const [loading, setLoading] = useState(false)
  async function onAsk() {
    setLoading(true)
    try { const r = await askRag(q); setAns(r.answer + (r.cites.length ? '\n\nCites: ' + r.cites.join(' • ') : '')) }
    catch (e: any) { setAns('Failed: ' + e.message) }
    finally { setLoading(false) }
  }
  return (
    <div>
      <div style={{ fontFamily: 'Space Grotesk', fontSize: 22, fontWeight: 800 }}>Intara Archives</div>
      <div style={{ color: 'var(--intara-muted)', fontSize: 12, marginTop: 4 }}>RAG over docs • pgvector <code>match_docs</code> • citations • groundedness</div>
      <div className="glass" style={{ marginTop: 16, padding: 14 }}>
        <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--intara-muted)' }}>Ask Intara archives</div>
        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask docs..." style={{ flex: 1, padding: '10px 12px', borderRadius: 12, border: '1px solid var(--intara-border)', background: 'rgba(255,255,255,0.06)', color: 'var(--intara-text)', fontSize: 13, outline: 'none' }} />
          <button onClick={onAsk} disabled={loading} className="btn-primary" style={{ padding: '10px 16px' }}>{loading ? '...' : 'Ask'}</button>
        </div>
        {ans && <pre className="code-block" style={{ marginTop: 12, background: 'rgba(255,255,255,0.04)', whiteSpace: 'pre-wrap' }}>{ans}</pre>}
      </div>
      <div className="glass" style={{ marginTop: 14, padding: 14 }}>
        <div style={{ fontSize: 12, fontWeight: 700 }}>How RAG works</div>
        <div style={{ fontSize: 12, color: 'var(--intara-muted)', marginTop: 6, lineHeight: 1.6 }}>
          Docs chunked 400 chars + 50 overlap → embed <code>gemini-embedding-001</code> (3072d, truncated/padded 1536 legacy) → pgvector <code>docs</code> → RPC <code>match_docs(query_embedding, match_count)</code> cosine via <code>&lt;=&gt;</code> → top 5 → Gemini synthesize with <code>Context + Q + Cite</code>. Cites are first 120 chars of docs.
        </div>
      </div>
    </div>
  )
}
