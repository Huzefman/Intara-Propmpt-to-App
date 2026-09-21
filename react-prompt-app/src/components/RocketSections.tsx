import { useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useReveal } from '../hooks/useReveal'

const pillars = [
  {
    id: '01',
    kicker: 'Wish',
    headline: 'The thinking before the build.',
    body: 'Describe any app idea, decision, or market itch. Intara returns requirements, entities, and a clear build plan — ready to approve, ready to weave from.',
    chips: ['Requirements', 'Entities', 'Build graph'],
    linkTo: '/',
    linkLabel: 'Explore the plan',
  },
  {
    id: '02',
    kicker: 'Forge',
    headline: 'Trial-grade from first prompt.',
    body: 'Build straight from the approved plan — no re-explaining, no lost context. Trial sandbox in your browser, runnable zip, one-command backend.',
    chips: ['Trial sandbox', 'Runnable zip', 'SQLite backend'],
    linkTo: '/constellation',
    linkLabel: 'Open a trial',
  },
  {
    id: '03',
    kicker: 'Archives',
    headline: 'Ask what Intara already knows.',
    body: 'Every wish and doc becomes searchable memory. Ask the archives and get grounded answers with citations — then take them straight into your next build.',
    chips: ['RAG over docs', 'pgvector', 'Citations'],
    linkTo: '/archives',
    linkLabel: 'Consult archives',
  },
]

const startingPoints = [
  { id: 'figure', label: 'I need to figure out what to build' },
  { id: 'build', label: "I'm ready to build" },
  { id: 'ask', label: 'I want to ask the archives' },
]

const steps = [
  {
    id: '01',
    title: 'Describe the wish.',
    body: 'Type any app idea. Add scope in plain words — Intara handles the rest.',
  },
  {
    id: '02',
    title: 'Approve the plan.',
    body: 'A structured brief with requirements, entities, and a build graph. Edit it or approve it as-is.',
  },
  {
    id: '03',
    title: 'Watch it weave — without starting over.',
    body: 'Pages and tables build sequentially with live step progress. The plan carries full context forward.',
  },
  {
    id: '04',
    title: 'Trial it and take it with you.',
    body: 'Click around the live trial, download the runnable zip, or point it at Supabase. Nothing is locked in.',
  },
]

export function Pillars() {
  const ref = useReveal<HTMLDivElement>()
  return (
    <div ref={ref} className="glass reveal" style={{ marginTop: 20, padding: 24, borderRadius: 20 }}>
      <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--intara-faint)' }}>
        The wishing · The forging · The remembering
      </div>
      <div className="text-display" style={{ fontSize: 'clamp(22px, 3.4vw, 30px)', fontWeight: 500, letterSpacing: '-0.03em', marginTop: 10, color: 'var(--intara-text)' }}>
        Three movements. One shared stardust.
      </div>
      <p style={{ color: 'var(--intara-faint)', fontSize: 13, marginTop: 8, maxWidth: 560, lineHeight: 1.7 }}>
        Start anywhere — Intara carries everything you already wished into your next step.
      </p>
      <div className="pillars-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, marginTop: 18 }}>
        {pillars.map((p, i) => (
          <motion.div
            key={p.id}
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-8% 0px' }}
            transition={{ duration: 0.55, delay: i * 0.08, ease: [0.16, 1, 0.3, 1] }}
            style={{ padding: 18, borderRadius: 16, border: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.02)', position: 'relative', overflow: 'hidden' }}
          >
            <div style={{ fontFamily: 'Space Grotesk', fontSize: 40, fontWeight: 600, letterSpacing: '-0.04em', color: 'rgba(255,255,255,0.07)', position: 'absolute', top: 6, right: 12, pointerEvents: 'none' }}>
              {p.id}
            </div>
            <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--intara-nebula-light)' }}>{p.id} · {p.kicker}</div>
            <div style={{ fontFamily: 'Space Grotesk', fontSize: 16, fontWeight: 500, letterSpacing: '-0.02em', marginTop: 8, color: 'var(--intara-text)' }}>{p.headline}</div>
            <div style={{ fontSize: 12, color: 'var(--intara-faint)', marginTop: 6, lineHeight: 1.65 }}>{p.body}</div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 12 }}>
              {p.chips.map((c) => (
                <span key={c} style={{ fontSize: 10.5, padding: '4px 9px', borderRadius: 999, border: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.03)', color: 'var(--intara-muted)' }}>{c}</span>
              ))}
            </div>
            <Link to={p.linkTo} style={{ display: 'inline-block', marginTop: 12, fontSize: 12, fontWeight: 550, color: 'var(--intara-nebula-light)', textDecoration: 'none' }}>
              {p.linkLabel} →
            </Link>
          </motion.div>
        ))}
      </div>
    </div>
  )
}

export function HowItWorks({ onStart }: { onStart: () => void }) {
  const ref = useReveal<HTMLDivElement>()
  const [active, setActive] = useState(1)
  return (
    <div ref={ref} className="glass reveal" style={{ marginTop: 16, padding: 24, borderRadius: 20 }}>
      <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--intara-faint)' }}>
        Pick your starting point
      </div>
      <div className="text-display" style={{ fontSize: 'clamp(20px, 3vw, 26px)', fontWeight: 500, letterSpacing: '-0.03em', marginTop: 10, color: 'var(--intara-text)' }}>
        Intara connects the rest.
      </div>
      <div style={{ display: 'flex', gap: 6, marginTop: 14, flexWrap: 'wrap' }} role="tablist" aria-label="Starting points">
        {startingPoints.map((s, i) => (
          <button
            key={s.id}
            role="tab"
            aria-selected={active === i}
            onClick={() => setActive(i)}
            style={{
              padding: '8px 14px', borderRadius: 999, fontSize: 12, fontWeight: active === i ? 600 : 450, cursor: 'pointer',
              border: active === i ? '1px solid rgba(139,92,246,0.9)' : '1px solid rgba(255,255,255,0.06)',
              background: active === i ? 'rgba(139,92,246,0.12)' : 'transparent',
              color: active === i ? 'var(--intara-nebula-light)' : 'var(--intara-faint)',
              transition: 'all 0.3s var(--ease-premium)',
            }}
          >
            {s.label}
          </button>
        ))}
      </div>
      <div className="steps-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginTop: 16 }}>
        {steps.map((s, i) => (
          <motion.div
            key={s.id}
            initial={{ opacity: 0, y: 14 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-8% 0px' }}
            transition={{ duration: 0.5, delay: i * 0.06, ease: [0.16, 1, 0.3, 1] }}
            style={{ padding: 14, borderRadius: 14, border: '1px solid rgba(255,255,255,0.05)', background: 'rgba(255,255,255,0.02)' }}
          >
            <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: 'var(--intara-nebula-light)', fontWeight: 600 }}>{s.id}</div>
            <div style={{ fontSize: 13, fontWeight: 600, letterSpacing: '-0.01em', marginTop: 6, color: 'var(--intara-text)' }}>{s.title}</div>
            <div style={{ fontSize: 11.5, color: 'var(--intara-faint)', marginTop: 6, lineHeight: 1.6 }}>{s.body}</div>
          </motion.div>
        ))}
      </div>
      <div style={{ marginTop: 16, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <button onClick={onStart} className="btn-primary" style={{ padding: '12px 20px', fontSize: 12.5 }}>Weave your first wish</button>
        <span style={{ fontSize: 11, color: 'var(--intara-dim)' }}>Plan approval → sequential build → trial &amp; download</span>
      </div>
    </div>
  )
}
