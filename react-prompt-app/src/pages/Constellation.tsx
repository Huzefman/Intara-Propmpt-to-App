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

  if (loading) return <div className="glass" style={{ padding: 40, textAlign: 'center', color: 'var(--intara-faint)', borderRadius: 20 }}>
    <div style={{ width: 28, height: 28, border: '2px solid rgba(255,255,255,0.06)', borderTopColor: 'var(--intara-nebula)', borderRadius: '50%', animation: 'spin 0.9s var(--ease-fluid) infinite', margin: '0 auto' }} />
    <div style={{ marginTop: 12, fontSize: 12.5, fontWeight: 450, letterSpacing: '-0.01em' }}>Charting constellation…</div>
    <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
  </div>

  return (
    <div style={{ animation: 'fade-in-fluid 0.5s var(--ease-premium) both' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'end', gap: 16, flexWrap: 'wrap', marginBottom: 18 }}>
        <div>
          <div style={{ fontFamily: 'Space Grotesk', fontSize: 26, fontWeight: 400, letterSpacing: '-0.03em', color: 'var(--intara-text)' }}>Constellation</div>
          <div style={{ color: 'var(--intara-faint)', fontSize: 12.5, fontWeight: 400, marginTop: 6, letterSpacing: '-0.01em' }}><span style={{ color: 'var(--intara-nebula-light)', fontWeight: 600 }}>{filtered.length}</span> wishes · each a star</div>
        </div>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter wishes…" style={{ padding: '10px 14px', borderRadius: 999, border: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.03)', color: 'var(--intara-text)', fontSize: 12.5, fontWeight: 400, width: 240, outline: 'none', transition: 'all 0.3s var(--ease-premium)' }} />
      </div>

      {/* Star map — premium fluid */}
      <div className="glass" style={{ padding: 12, marginBottom: 16, overflow: 'hidden', borderRadius: 20 }}>
        <div style={{ position: 'relative', height: 300, borderRadius: 14, overflow: 'hidden', background: 'radial-gradient(ellipse 700px 360px at 50% 18%, rgba(139,92,246,0.14), transparent 65%), #08080C', border: '1px solid rgba(255,255,255,0.04)' }}>
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
              const twinkle = 2.4 + ((hashString(r.id + 't') % 20) / 10)
              return (
                <Link key={r.id} to={`/wish/${r.id}`} style={{ textDecoration: 'none' }}>
                  <g className="star-twinkle" style={{ animationDelay: `${(hashString(r.id) % 24) / 10}s`, animationDuration: `${twinkle}s`, cursor: 'pointer' } as React.CSSProperties}>
                    <title>{r.prd?.appName || 'Wish'} — {r.prompt.slice(0, 80)}</title>
                    <circle cx={x} cy={y} r={size + 6} fill="rgba(139,92,246,0.12)" />
                    <circle cx={x} cy={y} r={size} fill="#f8fafc" stroke="rgba(139,92,246,0.7)" strokeWidth={1.5} />
                    <text x={x} y={y - size - 10} textAnchor="middle" fill="rgba(255,255,255,0.75)" fontSize={9} fontFamily="Space Grotesk, sans-serif">{(r.prd?.appName || r.prompt.slice(0, 18)).slice(0, 18)}</text>
                  </g>
                </Link>
              )
            })}
          </svg>
          {!filtered.length && <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', color: 'var(--intara-muted)', fontSize: 13 }}>No wishes yet — make your first wish on Intara.</div>}
        </div>
      </div>

      {/* List — premium minimal */}
      <div className="glass" style={{ overflow: 'hidden', borderRadius: 16 }}>
        <div style={{ padding: '12px 14px', borderBottom: '1px solid rgba(255,255,255,0.04)', fontSize: 10.5, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--intara-faint)' }}>Wishes · {filtered.length}</div>
        <div style={{ maxHeight: 420, overflow: 'auto' }}>
          {filtered.map((r) => (
            <Link key={r.id} to={`/wish/${r.id}`} style={{ display: 'block', padding: 16, borderBottom: '1px solid rgba(255,255,255,0.03)', textDecoration: 'none', transition: 'background 0.3s var(--ease-premium)' }}>
              <div style={{ fontSize: 13.5, fontWeight: 550, letterSpacing: '-0.02em', color: 'var(--intara-text)' }}>{r.prd?.appName || 'Wish'}</div>
              <div style={{ fontSize: 12, fontWeight: 400, color: 'var(--intara-faint)', marginTop: 4, lineHeight: 1.5 }}>{r.prompt}</div>
              <div style={{ marginTop: 10, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {(r.prd?.tables || []).map((t: any) => (
                  <span key={t.name} style={{ fontSize: 10.5, fontWeight: 450, border: '1px solid rgba(255,255,255,0.05)', padding: '4px 8px', borderRadius: 999, background: 'rgba(255,255,255,0.02)', color: 'var(--intara-faint)' }}>
                    <span style={{ color: 'var(--intara-muted)', fontWeight: 600 }}>{t.name}</span> · {(t.fields || []).map((f: any) => `${f.name}`).join(' · ')}
                  </span>
                ))}
              </div>
            </Link>
          ))}
          {!filtered.length && <div style={{ padding: 28, textAlign: 'center', color: 'var(--intara-dim)', fontSize: 12.5, fontWeight: 400 }}>No matches — try another filter.</div>}
        </div>
      </div>
    </div>
  )
}
