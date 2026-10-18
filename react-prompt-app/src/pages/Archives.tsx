import { useState } from 'react'
import { askRag, type RagAnswer } from '../api/client'

/** Grounded Q&A about the Intara project, answered from its own docs. */
const SUGGESTIONS = [
  'What is Intara?',
  'How does the build pipeline work?',
  'What are the eval numbers?',
  'What are Intara’s limitations?',
  'How do I run the demo?',
  'How does the runtime execute specs?',
]

const chip = (active = false): React.CSSProperties => ({
  padding: '7px 12px', borderRadius: 999, fontSize: 11.5, fontWeight: active ? 600 : 450,
  border: '1px solid ' + (active ? 'rgba(139,92,246,0.85)' : 'rgba(255,255,255,0.08)'),
  background: active ? 'linear-gradient(180deg, #8B5CF6, #7C3AED)' : 'rgba(255,255,255,0.03)',
  color: active ? '#fff' : 'var(--intara-muted)', cursor: 'pointer',
  transition: 'all 0.25s var(--ease-premium)', textAlign: 'left',
})

function Badge({ label, tone = 'default' }: { label: string; tone?: 'default' | 'nebula' | 'amber' | 'green' }) {
  const tones = {
    default: { border: 'rgba(255,255,255,0.08)', color: 'var(--intara-faint)', bg: 'rgba(255,255,255,0.02)' },
    nebula: { border: 'rgba(139,92,246,0.45)', color: 'var(--intara-nebula-light)', bg: 'rgba(139,92,246,0.08)' },
    amber: { border: 'rgba(251,191,36,0.35)', color: '#FCD34D', bg: 'rgba(251,191,36,0.06)' },
    green: { border: 'rgba(52,211,153,0.35)', color: '#6EE7B7', bg: 'rgba(52,211,153,0.06)' },
  }[tone]
  return (
    <span style={{ fontSize: 10.5, fontWeight: 500, letterSpacing: '0.02em', padding: '4px 9px', borderRadius: 999, border: `1px solid ${tones.border}`, color: tones.color, background: tones.bg, whiteSpace: 'nowrap' }}>
      {label}
    </span>
  )
}

export function Archives() {
  const [q, setQ] = useState('')
  const [res, setRes] = useState<RagAnswer | null>(null)
  const [asked, setAsked] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function ask(question?: string) {
    const text = (question ?? q).trim()
    if (!text || loading) return
    setQ(text)
    setAsked(text)
    setLoading(true)
    setErr(null)
    try {
      setRes(await askRag(text))
    } catch (e: any) {
      setErr(e?.message || 'The archives are unreachable right now.')
      setRes(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ animation: 'fade-in-fluid 0.5s var(--ease-premium) both', maxWidth: 860 }}>
      <div style={{ fontFamily: 'Space Grotesk', fontSize: 26, fontWeight: 400, letterSpacing: '-0.03em', color: 'var(--intara-text)' }}>Archives</div>
      <div style={{ color: 'var(--intara-faint)', fontSize: 12.5, fontWeight: 400, marginTop: 6, letterSpacing: '-0.01em' }}>
        Grounded answers about Intara from its own docs — pgvector retrieval, cited sources, synthesis on whichever free LLM has quota.
      </div>

      {/* Ask card */}
      <div className="glass" style={{ marginTop: 18, padding: 18, borderRadius: 20 }}>
        <label htmlFor="rag-q" style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)' }}>Ask the archives</label>
        <div style={{ display: 'flex', gap: 10, marginTop: 12, flexWrap: 'wrap' }}>
          <input
            id="rag-q"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') ask() }}
            placeholder="What is Intara?"
            disabled={loading}
            style={{ flex: 1, minWidth: 200, padding: '12px 14px', borderRadius: 14, border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(255,255,255,0.03)', color: 'var(--intara-text)', fontSize: 13, fontWeight: 400, outline: 'none', transition: 'border-color 0.3s var(--ease-premium)' }}
          />
          <button onClick={() => ask()} disabled={loading || !q.trim()} className="btn-primary" style={{ padding: '12px 20px', fontSize: 12.5 }}>
            {loading ? 'Consulting…' : 'Ask'}
          </button>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 14 }} aria-label="Suggested questions">
          {SUGGESTIONS.map((s) => (
            <button key={s} onClick={() => ask(s)} disabled={loading} style={chip(asked === s)}>{s}</button>
          ))}
        </div>
      </div>

      {/* Loading */}
      {loading && (
        <div className="glass" style={{ marginTop: 14, padding: 22, borderRadius: 18, display: 'flex', gap: 12, alignItems: 'center' }} role="status" aria-live="polite">
          <span style={{ width: 16, height: 16, border: '2px solid rgba(255,255,255,0.08)', borderTopColor: 'var(--intara-nebula)', borderRadius: '50%', animation: 'spin 0.9s var(--ease-fluid) infinite', display: 'inline-block' }} />
          <span style={{ fontSize: 12.5, color: 'var(--intara-faint)' }}>Retrieving sources and grounding the answer…</span>
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      )}

      {/* Error */}
      {err && !loading && (
        <div className="glass" style={{ marginTop: 14, padding: 16, borderRadius: 16, border: '1px solid rgba(248,113,113,0.35)', background: 'rgba(248,113,113,0.05)', fontSize: 12.5, color: '#FCA5A5' }} role="alert">
          {err}
        </div>
      )}

      {/* Answer */}
      {res && !loading && (
        <div className="glass" style={{ marginTop: 14, padding: 18, borderRadius: 18, animation: 'fade-in-fluid 0.4s var(--ease-premium) both' }} aria-live="polite">
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <Badge label={res.retrieval === 'vector' ? 'pgvector retrieval' : res.retrieval === 'lexical' ? 'lexical fallback' : 'no retrieval'} tone={res.retrieval === 'vector' ? 'nebula' : 'amber'} />
            {res.retrieval_detail === 'client-cosine' && <Badge label="client-side cosine (schema drift)" tone="amber" />}
            {res.provider && <Badge label={`answered by ${res.provider}${res.model ? ` · ${res.model}` : ''}`} tone="green" />}
            <Badge label={`${res.cites.length} source${res.cites.length === 1 ? '' : 's'}`} />
          </div>
          <div style={{ marginTop: 14, fontSize: 13.5, lineHeight: 1.85, color: 'var(--intara-text)', whiteSpace: 'pre-wrap', letterSpacing: '-0.01em' }}>
            {res.answer}
          </div>
          {res.cites.length > 0 && (
            <div style={{ marginTop: 16, borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: 14 }}>
              <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)', marginBottom: 10 }}>Sources</div>
              <div style={{ display: 'grid', gap: 8 }}>
                {res.cites.map((c, i) => (
                  <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 12, padding: '10px 12px' }} title={c}>
                    <span style={{ flexShrink: 0, fontSize: 10.5, fontWeight: 600, color: 'var(--intara-nebula-light)', background: 'rgba(139,92,246,0.1)', border: '1px solid rgba(139,92,246,0.3)', borderRadius: 8, padding: '2px 7px' }}>[{i + 1}]</span>
                    <span style={{ fontSize: 11.5, lineHeight: 1.65, color: 'var(--intara-muted)', display: '-webkit-box', WebkitLineClamp: 4, WebkitBoxOrient: 'vertical', overflow: 'hidden' as const }}>{c}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* How it works */}
      <div className="glass" style={{ marginTop: 14, padding: 16, borderRadius: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)' }}>How this works</div>
        <div style={{ fontSize: 12, fontWeight: 400, color: 'var(--intara-faint)', marginTop: 8, lineHeight: 1.8, letterSpacing: '-0.01em' }}>
          Question → embed (<code style={{ background: 'rgba(255,255,255,0.04)', padding: '1px 5px', borderRadius: 6 }}>gemini-embedding-001</code> or OpenRouter) → pgvector cosine
          <code style={{ background: 'rgba(255,255,255,0.04)', padding: '1px 5px', borderRadius: 6, margin: '0 4px' }}>match_docs</code> top 5 → synthesis on whichever free provider has quota, grounded strictly in the retrieved docs.
          If embeddings are unavailable the retrieval drops to a labelled BM25 lexical fallback — answers never silently search zero vectors.
        </div>
      </div>
    </div>
  )
}
