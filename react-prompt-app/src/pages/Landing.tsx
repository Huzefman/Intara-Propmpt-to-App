import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, useSpring, useTransform } from 'framer-motion'
import { PlanetOrb } from '../components/PlanetOrb'
import { WishInput } from '../components/WishInput'
import { Pillars, HowItWorks } from '../components/RocketSections'
import { createWish, createPlan, askRag, reconcileWish, PlanAbortedError } from '../api/client'
import { supabase } from '../supabase'
import { DEMO, GITHUB_URL } from '../demo'
import { useReveal } from '../hooks/useReveal'

const heroContainer = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08, delayChildren: 0.05 } },
}
const heroItem = {
  hidden: { opacity: 0, y: 18, filter: 'blur(6px)' },
  show: { opacity: 1, y: 0, filter: 'blur(0px)', transition: { duration: 0.7, ease: [0.16, 1, 0.3, 1] as const } },
}

function CountUp({ value }: { value: number }) {
  const spring = useSpring(0, { stiffness: 60, damping: 20 })
  const [display, setDisplay] = useState(0)
  useEffect(() => { spring.set(value) }, [value, spring])
  useEffect(() => spring.on('change', (v) => setDisplay(Math.round(v))), [spring])
  return <>{display.toLocaleString()}</>
}

const EXAMPLES = [
  'A task tracker with users, tasks, and due dates',
  'A minimalist blog with authors, posts, comments, and likes',
  'A recipe sharing app where users can save favorites and leave reviews',
  'An e-commerce wishlist with products, carts, and orders',
  'A booking system for salons with services, slots, and appointments',
  'A Q&A forum with questions, answers, votes, and tags',
  'A project management tool with projects, tasks, and team members',
  'A marketplace for freelancers with gigs, proposals, and payments',
]

export function Landing() {
  const nav = useNavigate()
  const [prompt, setPrompt] = useState(EXAMPLES[0])
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [weaveNote, setWeaveNote] = useState<string | null>(null)
  const [count, setCount] = useState<number | null>(null)
  const [q, setQ] = useState('What stack does Intara use?')
  const [ragAns, setRagAns] = useState('')

  useEffect(() => {
    if (DEMO) return
    supabase.from('wishes').select('id', { count: 'exact', head: true }).then(({ count }) => setCount(count ?? null)).then(() => {}, () => {})
  }, [])

  const [staged, setStaged] = useState(true)
  const wishRef = useRef<HTMLDivElement>(null)
  function scrollToWish() {
    wishRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  async function onWeave() {
    if (!prompt.trim()) return
    setLoading(true); setErr(null)
    const text = prompt.trim()
    try {
      const w = staged ? await createPlan(text) : await createWish(text)
      nav(`/wish/${w.id}`)
    } catch (e: any) {
      if (e instanceof PlanAbortedError) {
        // Slow plan, not a failure: the server keeps working. Reconcile —
        // land straight in the chat if the wish already exists.
        setWeaveNote('Still weaving — checking for your wish…')
        const found = await reconcileWish(text)
        if (found) {
          nav(`/wish/${found.id}`)
          return
        }
        setErr(e.message)
      } else {
        setErr(e.message || 'weave failed')
      }
    } finally { setLoading(false); setWeaveNote(null) }
  }

  async function onAsk() {
    try {
      const r = await askRag(q)
      setRagAns(r.answer + (r.cites.length ? '\n\nCites: ' + r.cites.join(' • ') : ''))
    } catch (e: any) { setRagAns('Archives unavailable: ' + e.message) }
  }

  const loreRef = useReveal<HTMLDivElement>()
  const archivesRef = useReveal<HTMLDivElement>()

  return (
    <div>
      {/* Hero — staggered entrance */}
      <motion.div className="hero-grid" variants={heroContainer} initial="hidden" animate="show" style={{ display: 'grid', gridTemplateColumns: '1.15fr auto', gap: 32, alignItems: 'center', marginBottom: 36 }}>
        <div>
          <motion.div variants={heroItem} style={{ fontFamily: 'Space Grotesk', fontSize: 'clamp(32px, 5vw, 44px)', fontWeight: 400, letterSpacing: '-0.04em', lineHeight: 0.95, color: 'var(--intara-text)' }}>
            Make a <span style={{ color: 'var(--intara-nebula-light)', fontWeight: 500, position: 'relative' }}>software wish
              <span style={{ position: 'absolute', left: 0, right: 0, bottom: -4, height: 1, background: 'linear-gradient(90deg, rgba(139,92,246,0.4), transparent)', opacity: 0.6 }} />
            </span><br />
            <span style={{ fontWeight: 300, color: 'var(--intara-muted)', letterSpacing: '-0.03em' }}>come true.</span>
          </motion.div>
          <motion.p variants={heroItem} style={{ color: 'var(--intara-faint)', fontSize: 14, fontWeight: 400, marginTop: 14, lineHeight: 1.7, maxWidth: 500, letterSpacing: '-0.01em' }}>
            Intara listens beyond the heliopause. Describe any app — task tracker, blog, salon booking — and watch schemas, frontend, backend and specs emerge as stardust. Minimal. Fluid. Runnable.
          </motion.p>
          <motion.div variants={heroItem} style={{ display: 'flex', gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
            {!DEMO && EXAMPLES.slice(0, 4).map((ex) => (
              <motion.button key={ex} whileHover={{ y: -2 }} whileTap={{ scale: 0.97 }} onClick={() => setPrompt(ex)} className="btn-ghost" style={{ fontSize: 11.5, fontWeight: 450, padding: '8px 12px', letterSpacing: '-0.01em' }}>{ex.slice(0, 34)}…</motion.button>
            ))}
          </motion.div>
          <motion.div variants={heroItem} style={{ marginTop: 14, fontSize: 11, fontWeight: 400, letterSpacing: '0.02em', color: 'var(--intara-dim)' }}>
            {DEMO ? (
              <><span style={{ color: 'var(--intara-nebula-light)', fontWeight: 600 }}>10 gold apps</span> · static demo · runs in your browser <span style={{ opacity: 0.3, margin: '0 8px' }}>·</span> 3.7 light years away</>
            ) : count !== null ? (
              <><span style={{ color: 'var(--intara-nebula-light)', fontWeight: 600 }}><CountUp value={count} /></span> wishes granted <span style={{ opacity: 0.3, margin: '0 8px' }}>·</span> 3.7 light years away</>
            ) : 'Intara listens from 3.7 light years away'}
          </motion.div>
          <motion.div variants={heroItem} style={{ display: 'flex', gap: 10, marginTop: 16, flexWrap: 'wrap' }}>
            {DEMO ? (
              <>
                <motion.button whileHover={{ y: -2 }} whileTap={{ scale: 0.98 }} onClick={() => nav('/templates')} className="btn-primary" style={{ fontSize: 12.5, padding: '11px 20px' }}>Open the 10 live apps</motion.button>
                <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="btn-ghost" style={{ fontSize: 12.5, padding: '11px 20px', textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}>Source on GitHub</a>
              </>
            ) : (
              <>
                <motion.button whileHover={{ y: -2 }} whileTap={{ scale: 0.98 }} onClick={scrollToWish} className="btn-primary" style={{ fontSize: 12.5, padding: '11px 20px' }}>Start weaving</motion.button>
                <motion.button whileHover={{ y: -2 }} whileTap={{ scale: 0.98 }} onClick={() => nav('/constellation')} className="btn-ghost" style={{ fontSize: 12.5 }}>View constellation</motion.button>
              </>
            )}
          </motion.div>
        </div>
        <motion.div variants={heroItem} style={{ display: 'grid', placeItems: 'center', padding: 8 }}>
          <PlanetOrb pulsing={loading} size={240} interactive />
        </motion.div>
      </motion.div>

      {!DEMO && (
        <>
          <div style={{ display: 'flex', gap: 8, marginBottom: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ fontSize: 11, fontWeight: 500, letterSpacing: '0.04em', textTransform: 'uppercase', color: staged ? 'var(--intara-nebula-light)' : 'var(--intara-dim)' }}>Build mode</span>
            <button onClick={() => setStaged(true)} style={{ padding: '6px 12px', borderRadius: 999, fontSize: 11.5, fontWeight: staged ? 600 : 450, border: staged ? '1px solid rgba(139,92,246,0.9)' : '1px solid rgba(255,255,255,0.06)', background: staged ? 'rgba(139,92,246,0.12)' : 'transparent', color: staged ? 'var(--intara-nebula-light)' : 'var(--intara-faint)', cursor: 'pointer' }}>Staged · plan → pages (detailed)</button>
            <button onClick={() => setStaged(false)} style={{ padding: '6px 12px', borderRadius: 999, fontSize: 11.5, fontWeight: !staged ? 600 : 450, border: !staged ? '1px solid rgba(255,255,255,0.12)' : '1px solid rgba(255,255,255,0.06)', background: !staged ? 'rgba(255,255,255,0.06)' : 'transparent', color: !staged ? 'var(--intara-text)' : 'var(--intara-faint)', cursor: 'pointer' }}>One-shot quick</button>
            <span style={{ fontSize: 10.5, color: 'var(--intara-dim)', marginLeft: 6 }}>{staged ? 'Clarity check → Q&A → plan approval → sequential build → live trial' : 'Single prompt → artifacts'}</span>
          </div>
          <div ref={wishRef} style={{ scrollMarginTop: 90 }}>
            <WishInput value={prompt} onChange={setPrompt} onSubmit={onWeave} loading={loading} placeholder={staged ? "I wish for a hackathon manager with teams, projects, votes..." : "I wish for a..."} autoFocus />
          </div>
        </>
      )}
      {DEMO && (
        <div className="glass" style={{ padding: 18, borderRadius: 18, display: 'grid', gap: 10 }}>
          <div style={{ fontSize: 13, fontWeight: 550, fontFamily: 'Space Grotesk', letterSpacing: '-0.02em' }}>This is the static demo — the builder itself runs locally</div>
          <div style={{ fontSize: 12, fontWeight: 400, color: 'var(--intara-faint)', lineHeight: 1.7, letterSpacing: '-0.01em' }}>
            The full pipeline (wish → validated spec → gates → runnable app) needs the FastAPI backend and LLM keys.
            Here you can open the <span style={{ color: 'var(--intara-muted)' }}>10 human-reviewed gold apps</span> and use every block —
            create rows, filter, drag cards, switch roles, export CSV, print — all executed by the spec runtime in your browser.
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn-primary" onClick={() => nav('/templates')} style={{ fontSize: 12.5 }}>Open the live apps</button>
            <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="btn-ghost" style={{ fontSize: 12.5, textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}>Source on GitHub</a>
          </div>
        </div>
      )}
      {err && <div style={{ marginTop: 12, fontSize: 12.5, fontWeight: 450, color: '#FCA5A5', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.14)', padding: '12px 14px', borderRadius: 14, backdropFilter: 'blur(12px)' }}>{err} <button onClick={() => nav('/constellation')} className="btn-ghost btn-sm" style={{ marginLeft: 8 }}>Open Constellation</button></div>}
      {weaveNote && !err && <div style={{ marginTop: 12, fontSize: 12.5, color: 'var(--intara-nebula-light)' }}>{weaveNote}</div>}

      <Pillars />
      <HowItWorks onStart={() => window.scrollTo({ top: 0, behavior: 'smooth' })} />

      {/* Lore — scroll reveal */}
      <div ref={loreRef} className="glass reveal" style={{ marginTop: 20, padding: 16, display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
        <img src="/assets/constellation.png" alt="" width={64} height={64} style={{ borderRadius: 14, objectFit: 'cover', opacity: 0.88, border: '1px solid rgba(255,255,255,0.06)' }} onError={(e) => (e.currentTarget.style.display = 'none')} />
        <div style={{ flex: 1, minWidth: 220 }}>
          <div style={{ fontSize: 13, fontWeight: 550, fontFamily: 'Space Grotesk', letterSpacing: '-0.02em', color: 'var(--intara-text)' }}>Your wish drifts. Intara weaves.</div>
          <div style={{ fontSize: 12, fontWeight: 400, color: 'var(--intara-faint)', marginTop: 4, lineHeight: 1.6, letterSpacing: '-0.01em' }}>
            <span style={{ color: 'var(--intara-muted)', fontWeight: 500 }}>Schemas</span> · <span style={{ color: 'var(--intara-muted)', fontWeight: 500 }}>Frontend</span> · <span style={{ color: 'var(--intara-muted)', fontWeight: 500 }}>Backend</span> · Scroll
            <span style={{ opacity: 0.4, margin: '0 8px' }}>·</span> Runnable zip · shareable link · Trial in browser
          </div>
        </div>
        <img src="/assets/nebula-gradient.png" alt="" width={88} height={64} style={{ borderRadius: 14, objectFit: 'cover', opacity: 0.6 }} onError={(e) => (e.currentTarget.style.display = 'none')} />
      </div>

      {/* Archives — scroll reveal */}
      {!DEMO && (
      <div ref={archivesRef} className="glass reveal" style={{ marginTop: 16, padding: 16 }}>
        <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--intara-faint)' }}>Consult archives — RAG</div>
        <div style={{ display: 'flex', gap: 10, marginTop: 12, flexWrap: 'wrap' }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask what stack Intara uses…" style={{ flex: 1, minWidth: 200, padding: '12px 14px', borderRadius: 14, border: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.03)', color: 'var(--intara-text)', fontSize: 13, fontWeight: 400, outline: 'none', transition: 'all 0.3s var(--ease-premium)' }} />
          <button onClick={onAsk} className="btn-primary" style={{ padding: '12px 18px', fontSize: 12.5 }}>Ask</button>
        </div>
        {ragAns && <pre className="code-block" style={{ marginTop: 12, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)' }}>{ragAns}</pre>}
      </div>
      )}
    </div>
  )
}
