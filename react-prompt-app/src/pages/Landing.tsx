import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PlanetOrb } from '../components/PlanetOrb'
import { WishInput } from '../components/WishInput'
import { createWish, askRag } from '../api/client'
import { supabase } from '../supabase'

const EXAMPLES = [
  'A task tracker with users, tasks, and due dates',
  'A minimalist blog with authors, posts, comments, and likes',
  'An e-commerce wishlist with products, carts, and orders',
  'A booking system for salons with services, slots, and appointments',
  'A Q&A forum with questions, answers, votes, and tags',
]

export function Landing() {
  const nav = useNavigate()
  const [prompt, setPrompt] = useState(EXAMPLES[0])
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [count, setCount] = useState<number | null>(null)
  const [q, setQ] = useState('What stack does Intara use?')
  const [ragAns, setRagAns] = useState('')

  useEffect(() => {
    supabase.from('wishes').select('id', { count: 'exact', head: true }).then(({ count }) => setCount(count ?? null)).then(() => {}, () => {})
  }, [])

  async function onWeave() {
    if (!prompt.trim()) return
    setLoading(true); setErr(null)
    try {
      const w = await createWish(prompt)
      nav(`/wish/${w.id}`)
    } catch (e: any) {
      setErr(e.message || 'weave failed')
    } finally { setLoading(false) }
  }

  async function onAsk() {
    try {
      const r = await askRag(q)
      setRagAns(r.answer + (r.cites.length ? '\n\nCites: ' + r.cites.join(' • ') : ''))
    } catch (e: any) { setRagAns('Archives unavailable: ' + e.message) }
  }

  return (
    <div>
      {/* Hero */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 24, alignItems: 'center', marginBottom: 28 }}>
        <div>
          <div style={{ fontFamily: 'Space Grotesk', fontSize: 42, fontWeight: 800, letterSpacing: '-.04em', lineHeight: 1 }}>
            Make a <span style={{ color: '#8B5CF6' }}>software wish</span><br />come true.
          </div>
          <p style={{ color: 'var(--intara-muted)', fontSize: 14, marginTop: 10, lineHeight: 1.6, maxWidth: 520 }}>
            Intara is a planet that listens. Describe any app — task tracker, blog, salon booking — and Intara weaves schemas, frontend, backend, and specs as stardust. One wish, four artifacts. No boilerplate.
          </p>
          <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
            {EXAMPLES.slice(0, 3).map((ex) => (
              <button key={ex} onClick={() => setPrompt(ex)} className="btn-ghost" style={{ fontSize: 11, padding: '7px 10px' }}>{ex.slice(0, 36)}…</button>
            ))}
          </div>
          <div style={{ marginTop: 8, fontSize: 11, color: 'var(--intara-faint)' }}>
            {count !== null ? `${count} wishes granted • Intara listens from 3.7 light years away` : 'Intara listens from 3.7 light years away'}
          </div>
        </div>
        <div style={{ display: 'grid', placeItems: 'center', padding: 12 }}>
          <PlanetOrb pulsing={loading} size={220} />
        </div>
      </div>

      <WishInput value={prompt} onChange={setPrompt} onSubmit={onWeave} loading={loading} placeholder="I wish for a..." autoFocus />
      {err && <div style={{ marginTop: 10, fontSize: 12, color: '#f87171', background: 'rgba(239,68,68,0.10)', border: '1px solid rgba(239,68,68,0.20)', padding: '10px 12px', borderRadius: 12 }}>{err}</div>}

      {/* Lore strip */}
      <div className="glass" style={{ marginTop: 18, padding: 14, display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
        <img src="/assets/constellation.png" alt="" width={72} height={72} style={{ borderRadius: 12, objectFit: 'cover', opacity: 0.9, border: '1px solid var(--intara-border)' }} onError={(e) => (e.currentTarget.style.display = 'none')} />
        <div style={{ flex: 1, minWidth: 220 }}>
          <div style={{ fontSize: 13, fontWeight: 700, fontFamily: 'Space Grotesk' }}>Your wish drifts. Intara weaves.</div>
          <div style={{ fontSize: 12, color: 'var(--intara-muted)', marginTop: 4 }}>Intara forges: <b>Schemas</b> (prisma + sql) • <b>Frontend</b> (Vite React) • <b>Backend</b> (FastAPI) • <b>Scroll</b> (PRD + OpenAPI + cites). Runnable zip, shareable link. <span style={{ color: 'var(--intara-faint)' }}>No preview/deploy in v1 — pure artifacts.</span></div>
        </div>
        <img src="/assets/nebula-gradient.png" alt="" width={96} height={72} style={{ borderRadius: 12, objectFit: 'cover', opacity: 0.7 }} onError={(e) => (e.currentTarget.style.display = 'none')} />
      </div>

      {/* Archives (RAG) */}
      <div className="glass" style={{ marginTop: 16, padding: 14 }}>
        <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--intara-muted)' }}>Consult Intara archives — RAG</div>
        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask archives..." style={{ flex: 1, padding: '10px 12px', borderRadius: 12, border: '1px solid var(--intara-border)', background: 'rgba(255,255,255,0.06)', color: 'var(--intara-text)', fontSize: 13, outline: 'none' }} />
          <button onClick={onAsk} className="btn-primary" style={{ padding: '10px 16px' }}>Ask</button>
        </div>
        {ragAns && <pre className="code-block" style={{ marginTop: 10, background: 'rgba(255,255,255,0.04)' }}>{ragAns}</pre>}
      </div>
    </div>
  )
}
