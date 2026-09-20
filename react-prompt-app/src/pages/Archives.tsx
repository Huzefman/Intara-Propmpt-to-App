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
    <div style={{ animation: 'fade-in-fluid 0.5s var(--ease-premium) both' }}>
      <div style={{ fontFamily: 'Space Grotesk', fontSize: 26, fontWeight: 400, letterSpacing: '-0.03em', color: 'var(--intara-text)' }}>Archives</div>
      <div style={{ color: 'var(--intara-faint)', fontSize: 12.5, fontWeight: 400, marginTop: 6, letterSpacing: '-0.01em' }}>RAG · pgvector · <code style={{ background: 'rgba(255,255,255,0.04)', padding: '2px 6px', borderRadius: 6, fontSize: 11 }}>match_docs</code> · citations · groundedness</div>
      <div className="glass" style={{ marginTop: 18, padding: 18, borderRadius: 20 }}>
        <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)' }}>Ask Intara archives</div>
        <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="What stack does Intara use?" style={{ flex: 1, padding: '12px 14px', borderRadius: 14, border: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.03)', color: 'var(--intara-text)', fontSize: 13, fontWeight: 400, outline: 'none', transition: 'all 0.3s var(--ease-premium)' }} />
          <button onClick={onAsk} disabled={loading} className="btn-primary" style={{ padding: '12px 18px', fontSize: 12.5 }}>{loading ? '…' : 'Ask'}</button>
        </div>
        {ans && <pre className="code-block" style={{ marginTop: 14, background: '#08080C', border: '1px solid rgba(255,255,255,0.04)' }}>{ans}</pre>}
      </div>
      <div className="glass" style={{ marginTop: 14, padding: 16, borderRadius: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)' }}>How RAG works</div>
        <div style={{ fontSize: 12, fontWeight: 400, color: 'var(--intara-faint)', marginTop: 8, lineHeight: 1.7, letterSpacing: '-0.01em' }}>
          Docs <span style={{ color: 'var(--intara-muted)' }}>400</span> + overlap <span style={{ color: 'var(--intara-muted)' }}>50</span> → embed <code style={{ background: 'rgba(255,255,255,0.04)', padding: '1px 5px', borderRadius: 6 }}>gemini-embedding-001</code> 3072 → pgvector <code style={{ background: 'rgba(255,255,255,0.04)', padding: '1px 5px', borderRadius: 6 }}>docs</code> → <code style={{ background: 'rgba(255,255,255,0.04)', padding: '1px 5px', borderRadius: 6 }}>match_docs</code> cosine <code>&lt;=&gt;</code> top 5 → Gemini synthesize.
        </div>
      </div>
    </div>
  )
}
