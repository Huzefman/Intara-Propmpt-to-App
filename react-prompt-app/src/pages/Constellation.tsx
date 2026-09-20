import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { supabase } from '../supabase'
import { hashString } from '../lib/hash'

type WishRow = { id: string; prompt: string; prd: any; created_at: string }

export function Constellation() {
  const [rows, setRows] = useState<WishRow[]>([])
  const [loading, setLoading] = useState(true)
  const [q, setQ] = useState('')

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      let got = false
      try {
        const { data, error } = await supabase.from('wishes').select('id,prompt,prd,created_at').order('created_at', { ascending: false }).limit(50)
        if (!cancelled && !error && data && data.length) { setRows(data as any); got = true }
      } catch {}
      if (!got && !cancelled) {
        try {
          const r = await fetch('/api/wishes')
          if (r.ok) {
            const j = await r.json()
            if (Array.isArray(j) && j.length) setRows(j.map((w: any) => ({ id: w.id, prompt: w.prompt, prd: w.prd, created_at: w.created_at })))
          }
        } catch {}
      }
      if (!cancelled) setLoading(false)
    }
    load()
    return () => { cancelled = true }
  }, [])

  const filtered = rows.filter(r => !q || r.prompt.toLowerCase().includes(q.toLowerCase()) || (r.prd?.appName || '').toLowerCase().includes(q.toLowerCase()))

  if (loading) return <div className="glass" style={{ padding: 24, textAlign: 'center', color: 'var(--intara-muted)' }}>Charting constellation…</div>

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'end', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
        <div>
          <div style={{ fontFamily: 'Space Grotesk', fontSize: 22, fontWeight: 800 }}>My Constellation</div>
          <div style={{ color: 'var(--intara-muted)', fontSize: 12, marginTop: 4 }}>{filtered.length} wishes • Each wish is a star</div>
        </div>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter wishes..." style={{ padding: '9px 12px', borderRadius: 999, border: '1px solid var(--intara-border)', background: 'rgba(255,255,255,0.06)', color: 'var(--intara-text)', fontSize: 12, width: 220 }} />
      </div>

      {/* Star map SVG */}
      <div className="glass" style={{ padding: 12, marginBottom: 16, overflow: 'hidden' }}>
        <div style={{ position: 'relative', height: 280, borderRadius: 12, overflow: 'hidden', background: 'radial-gradient(ellipse 600px 300px at 50% 20%, rgba(139,92,246,0.18), transparent), #0f0f1a', border: '1px solid var(--intara-border)' }}>
          <img src="/assets/constellation.png" alt="" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: 0.18, pointerEvents: 'none' }} onError={(e) => (e.currentTarget.style.display = 'none')} />
          <svg viewBox="0 0 1000 280" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
            {/* constellation lines */}
            {filtered.slice(0, 12).map((_, i, arr) => {
              if (i + 1 >= arr.length) return null
              const a = filtered[i], b = filtered[i + 1]
              const ax = (hashString(a.id) % 900) + 50, ay = (hashString(a.id + 'y') % 180) + 50
              const bx = (hashString(b.id) % 900) + 50, by = (hashString(b.id + 'y') % 180) + 50
              return <line key={i} x1={ax} y1={ay} x2={bx} y2={by} stroke="rgba(255,255,255,0.10)" strokeWidth={1} />
            })}
            {filtered.slice(0, 20).map((r) => {
              const x = (hashString(r.id) % 900) + 50
              const y = (hashString(r.id + 'y') % 180) + 50
              const size = 4 + (hashString(r.prd?.appName || r.prompt) % 5)
              return (
                <g key={r.id}>
                  <circle cx={x} cy={y} r={size + 6} fill="rgba(139,92,246,0.12)" />
                  <circle cx={x} cy={y} r={size} fill="#f8fafc" stroke="rgba(139,92,246,0.7)" strokeWidth={1.5} />
                  <text x={x} y={y - size - 10} textAnchor="middle" fill="rgba(255,255,255,0.75)" fontSize={9} fontFamily="Space Grotesk, sans-serif">{(r.prd?.appName || r.prompt.slice(0, 18)).slice(0, 18)}</text>
                </g>
              )
            })}
          </svg>
          {!filtered.length && <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', color: 'var(--intara-muted)', fontSize: 13 }}>No wishes yet — make your first wish on Intara.</div>}
        </div>
      </div>

      {/* List */}
      <div className="glass" style={{ overflow: 'hidden' }}>
        <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--intara-border)', fontSize: 11, fontWeight: 800, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--intara-muted)' }}>Wishes • {filtered.length}</div>
        <div style={{ maxHeight: 420, overflow: 'auto' }}>
          {filtered.map((r) => (
            <Link key={r.id} to={`/wish/${r.id}`} style={{ display: 'block', padding: 14, borderBottom: '1px solid rgba(255,255,255,0.06)', textDecoration: 'none' }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--intara-text)' }}>{r.prd?.appName || 'Wish'}</div>
              <div style={{ fontSize: 12, color: 'var(--intara-muted)', marginTop: 4 }}>{r.prompt}</div>
              <div style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {(r.prd?.tables || []).map((t: any) => (
                  <span key={t.name} style={{ fontSize: 11, border: '1px solid var(--intara-border)', padding: '3px 7px', borderRadius: 999, background: 'rgba(255,255,255,0.04)', color: 'var(--intara-muted)' }}>
                    <b style={{ color: 'var(--intara-text)' }}>{t.name}</b> — {(t.fields || []).map((f: any) => `${f.name}:${f.type}`).join(', ')}
                  </span>
                ))}
              </div>
            </Link>
          ))}
          {!filtered.length && <div style={{ padding: 24, textAlign: 'center', color: 'var(--intara-faint)', fontSize: 13 }}>No matches. Try another query.</div>}
        </div>
      </div>
    </div>
  )
}
