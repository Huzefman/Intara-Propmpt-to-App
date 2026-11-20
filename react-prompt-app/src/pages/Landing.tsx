import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { PlanetOrb } from '../components/PlanetOrb'
import { WishInput } from '../components/WishInput'
import { Pillars, HowItWorks } from '../components/RocketSections'
import { askRag, createWishShell, startRun, clarifyWish, type ClarifyResponse } from '../api/client'
import { DEMO, GITHUB_URL } from '../demo'
import { useAuth } from '../hooks/useAuth'
import { useReveal } from '../hooks/useReveal'

const heroContainer = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08, delayChildren: 0.05 } },
}
const heroItem = {
  hidden: { opacity: 0, y: 18, filter: 'blur(6px)' },
  show: { opacity: 1, y: 0, filter: 'blur(0px)', transition: { duration: 0.7, ease: [0.16, 1, 0.3, 1] as const } },
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
  const { user, loading: authLoading } = useAuth(!DEMO)
  const [prompt, setPrompt] = useState(EXAMPLES[0])
  const [loading, setLoading] = useState(false)
  const [building, setBuilding] = useState(false)
  const [clarify, setClarify] = useState<ClarifyResponse | null>(null)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [appName, setAppName] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [q, setQ] = useState('What stack does Intara use?')
  const [ragAns, setRagAns] = useState('')

  const wishRef = useRef<HTMLDivElement>(null)
  function scrollToWish() {
    wishRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  async function onWeave() {
    if (!prompt.trim()) return
    if (!DEMO && !user) { nav('/auth?mode=signup'); return }
    if (DEMO) { nav('/templates'); return }
    setLoading(true); setErr(null)
    const text = prompt.trim()
    try {
      const data = await clarifyWish(text)
      setClarify(data)
      setAppName(data.appName || 'App')
      setAnswers({})
    } catch (e: any) {
      console.warn('clarify failed, falling back directly to build', e)
      try {
        const w = await createWishShell(text)
        const r = await startRun(text, 'App', w.id)
        nav(`/runs/${r.run_id}`)
      } catch (err2: any) {
        setErr(err2.message || 'weave failed')
      }
    } finally { setLoading(false) }
  }

  async function onStartBuild(skipAnswers = false) {
    if (!prompt.trim()) return
    setBuilding(true); setErr(null)
    const basePrompt = prompt.trim()
    let refined = basePrompt
    if (!skipAnswers && clarify?.questions?.length) {
      const chosen = Object.entries(answers).filter(([, v]) => !!v)
      if (chosen.length > 0) {
        const qMap = Object.fromEntries(clarify.questions.map((q) => [q.id, q.q]))
        const bullets = chosen.map(([qid, ans]) => `${qMap[qid] || qid}: ${ans}`)
        refined = `${basePrompt}\n\nKey Choices:\n- ` + bullets.join('\n- ')
      }
    }
    try {
      const chosenName = appName.trim() || clarify?.appName || 'App'
      const w = await createWishShell(basePrompt)
      const r = await startRun(refined, chosenName, w.id)
      nav(`/runs/${r.run_id}`)
    } catch (e: any) {
      setErr(e.message || 'build failed')
    } finally {
      setBuilding(false)
    }
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
            ) : (
              <><span style={{ color: 'var(--intara-nebula-light)', fontWeight: 600 }}>Private by default</span> · every wish is scoped to your account <span style={{ opacity: 0.3, margin: '0 8px' }}>·</span> 3.7 light years away</>
            )}
          </motion.div>
          <motion.div variants={heroItem} style={{ display: 'flex', gap: 10, marginTop: 16, flexWrap: 'wrap' }}>
            {DEMO ? (
              <>
                <motion.button whileHover={{ y: -2 }} whileTap={{ scale: 0.98 }} onClick={() => nav('/templates')} className="btn-primary" style={{ fontSize: 12.5, padding: '11px 20px' }}>Open the 10 live apps</motion.button>
                <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="btn-ghost" style={{ fontSize: 12.5, padding: '11px 20px', textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}>Source on GitHub</a>
              </>
            ) : authLoading ? (
              <button className="btn-ghost" disabled style={{ fontSize: 12.5, padding: '11px 20px', opacity: 0.6 }}>Checking your orbit…</button>
            ) : user ? (
              <>
                <motion.button whileHover={{ y: -2 }} whileTap={{ scale: 0.98 }} onClick={scrollToWish} className="btn-primary" style={{ fontSize: 12.5, padding: '11px 20px' }}>Start weaving</motion.button>
                <motion.button whileHover={{ y: -2 }} whileTap={{ scale: 0.98 }} onClick={() => nav('/constellation')} className="btn-ghost" style={{ fontSize: 12.5 }}>View constellation</motion.button>
              </>
            ) : (
              <>
                <motion.button whileHover={{ y: -2 }} whileTap={{ scale: 0.98 }} onClick={() => nav('/auth?mode=signup')} className="btn-primary" style={{ fontSize: 12.5, padding: '11px 20px' }}>Create an account to weave</motion.button>
                <motion.button whileHover={{ y: -2 }} whileTap={{ scale: 0.98 }} onClick={() => nav('/auth')} className="btn-ghost" style={{ fontSize: 12.5 }}>Sign in</motion.button>
              </>
            )}
          </motion.div>
        </div>
        <motion.div variants={heroItem} style={{ display: 'grid', placeItems: 'center', padding: 8 }}>
          <PlanetOrb pulsing={loading} size={240} interactive />
        </motion.div>
      </motion.div>

      {!DEMO && !authLoading && user && (
        <>
          <div style={{ display: 'flex', gap: 8, marginBottom: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ fontSize: 11, fontWeight: 500, letterSpacing: '0.04em', textTransform: 'uppercase', color: 'var(--intara-nebula-light)' }}>Spec build</span>
            <span style={{ fontSize: 10.5, color: 'var(--intara-dim)' }}>Prompt → typed App Spec → composed from prebuilt blocks → live app</span>
          </div>
          <div ref={wishRef} style={{ scrollMarginTop: 90 }}>
            {!clarify ? (
              <>
                <WishInput value={prompt} onChange={setPrompt} onSubmit={onWeave} loading={loading} placeholder="I wish for a hackathon manager with teams, projects, votes..." autoFocus />
                <div className="starter-wishes" style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12, alignItems: 'center' }}>
                  <span style={{ fontSize: 11, fontWeight: 500, color: 'var(--intara-muted)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                    ✦ Try an example:
                  </span>
                  {[
                    { label: '🩺 Vet Clinic & Visits', prompt: 'Veterinary clinic manager with patients, pet owners, appointments, and medical visit records' },
                    { label: '📦 Warehouse Stock & Alerts', prompt: 'Warehouse inventory tracker with stock items, suppliers, reorder thresholds, and restock logs' },
                    { label: '📋 Personal Taskflow & Habits', prompt: 'Personal habit and task manager with priority tags, daily streaks, and completion notes' },
                    { label: '💼 Client CRM & Deals Pipeline', prompt: 'CRM lead tracker with client contacts, deal stages, pipeline values, and follow-up activities' },
                  ].map((starter, idx) => (
                    <button
                      key={idx}
                      type="button"
                      className="starter-pill"
                      onClick={() => {
                        setPrompt(starter.prompt)
                        if (wishRef.current) wishRef.current.scrollIntoView({ behavior: 'smooth' })
                      }}
                    >
                      {starter.label}
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <motion.div
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                className="glass"
                style={{ padding: 24, borderRadius: 20, display: 'grid', gap: 16 }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
                  <div>
                    <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--intara-nebula-light)' }}>
                      Surface Analysis & Clarification
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 4 }}>
                      <input
                        value={appName}
                        onChange={(e) => setAppName(e.target.value)}
                        style={{ fontFamily: 'Space Grotesk', fontSize: 20, fontWeight: 600, background: 'transparent', border: 'none', borderBottom: '1px dashed rgba(255,255,255,0.2)', color: 'var(--intara-text)', padding: '2px 0', minWidth: 200 }}
                        placeholder="App Name"
                        title="Click to rename your app"
                      />
                      <span style={{ fontSize: 11, color: 'var(--intara-dim)' }}>✎ rename</span>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span className="pill" style={{ background: 'rgba(139,92,246,0.15)', color: 'var(--intara-nebula-light)', border: '1px solid rgba(139,92,246,0.3)' }}>
                      Clarity score: {clarify.score}/100
                    </span>
                  </div>
                </div>

                <div style={{ fontSize: 13, color: 'var(--intara-muted)', lineHeight: 1.6 }}>
                  {clarify.tagline}
                  {clarify.summary && <div style={{ fontSize: 12, color: 'var(--intara-faint)', marginTop: 4 }}>{clarify.summary}</div>}
                </div>

                {clarify.questions?.length > 0 && (
                  <div style={{ display: 'grid', gap: 14, marginTop: 4 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--intara-text)' }}>
                      A few quick choices so Intara composes the right compiler components:
                    </div>
                    {clarify.questions.map((q, i) => (
                      <div key={q.id || i} className="thread-q" style={{ marginTop: 0 }}>
                        <div className="thread-q-title" style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                          <span className="thread-q-num" style={{ background: 'rgba(139,92,246,0.2)', padding: '2px 6px', borderRadius: 6, fontSize: 11, fontWeight: 600 }}>{String(i + 1).padStart(2, '0')}</span>
                          <span>{q.q}</span>
                        </div>
                        <div className="thread-opts" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 8 }}>
                          {(q.options || []).map((o) => {
                            const isSelected = answers[q.id] === o.label
                            return (
                              <button
                                key={o.label}
                                type="button"
                                className={`thread-opt ${isSelected ? 'selected' : ''}`}
                                onClick={() => setAnswers((prev) => ({ ...prev, [q.id]: isSelected ? '' : o.label }))}
                                style={{ textAlign: 'left', cursor: 'pointer' }}
                              >
                                <div style={{ fontWeight: 600, color: isSelected ? 'var(--intara-nebula-light)' : 'var(--intara-text)' }}>
                                  {isSelected ? '✓ ' : ''}{o.label}
                                </div>
                                {o.desc && <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>{o.desc}</div>}
                              </button>
                            )
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {err && <div className="run-error" role="alert">{err}</div>}

                <div style={{ display: 'flex', gap: 10, marginTop: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  <button
                    className="btn-primary"
                    onClick={() => onStartBuild(false)}
                    disabled={building}
                    style={{ padding: '11px 22px' }}
                  >
                    {building ? 'Weaving your app…' : `Build App${Object.values(answers).filter(Boolean).length ? ` (${Object.values(answers).filter(Boolean).length} chosen)` : ''} →`}
                  </button>
                  <button
                    className="btn-ghost"
                    onClick={() => onStartBuild(true)}
                    disabled={building}
                    style={{ padding: '11px 18px' }}
                  >
                    Build without answering →
                  </button>
                  <button
                    className="btn-ghost"
                    onClick={() => { setClarify(null); setAnswers({}) }}
                    disabled={building}
                    style={{ fontSize: 12, opacity: 0.8 }}
                  >
                    ← Edit wish
                  </button>
                </div>
              </motion.div>
            )}
          </div>
        </>
      )}
      {!DEMO && !authLoading && !user && (
        <div ref={wishRef} className="glass" style={{ padding: 22, borderRadius: 20, display: 'grid', gap: 12, scrollMarginTop: 90 }}>
          <div style={{ fontFamily: 'Space Grotesk', fontSize: 18, fontWeight: 400, letterSpacing: '-0.03em', color: 'var(--intara-text)' }}>Your own private constellation</div>
          <div style={{ fontSize: 12.5, fontWeight: 400, color: 'var(--intara-faint)', lineHeight: 1.75, letterSpacing: '-0.01em', maxWidth: 620 }}>
            Create an account to make wishes, review plans and build runnable apps. Your plans, build history and chats live under your account only — other visitors never see them. The template gallery stays free to explore.
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn-primary" onClick={() => nav('/auth?mode=signup')} style={{ fontSize: 12.5 }}>Create my account</button>
            <button className="btn-ghost" onClick={() => nav('/auth')} style={{ fontSize: 12.5 }}>I already have one</button>
            <button className="btn-ghost" onClick={() => nav('/templates')} style={{ fontSize: 12.5 }}>Explore the 10 apps</button>
          </div>
        </div>
      )}
      {DEMO && (
        <div className="glass" style={{ padding: 18, borderRadius: 18, display: 'grid', gap: 10 }}>
          <div style={{ fontSize: 13, fontWeight: 550, fontFamily: 'Space Grotesk', letterSpacing: '-0.02em' }}>This is the static demo — the builder itself runs locally</div>
          <div style={{ fontSize: 12, fontWeight: 400, color: 'var(--intara-faint)', lineHeight: 1.7, letterSpacing: '-0.01em' }}>
            The full pipeline (wish → validated spec → gates → runnable app) needs the FastAPI backend and LLM keys.
            Here you can open the <span style={{ color: 'var(--intara-muted)' }}>10 curated gold apps</span> and use every block —
            create rows, filter, drag cards, switch roles, export CSV, print — all executed by the spec runtime in your browser.
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn-primary" onClick={() => nav('/templates')} style={{ fontSize: 12.5 }}>Open the live apps</button>
            <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="btn-ghost" style={{ fontSize: 12.5, textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}>Source on GitHub</a>
          </div>
        </div>
      )}
      {err && <div style={{ marginTop: 12, fontSize: 12.5, fontWeight: 450, color: '#FCA5A5', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.14)', padding: '12px 14px', borderRadius: 14, backdropFilter: 'blur(12px)' }}>{err} {user && <button onClick={() => nav('/constellation')} className="btn-ghost btn-sm" style={{ marginLeft: 8 }}>Open Constellation</button>}</div>}

      <Pillars />
      <HowItWorks onStart={() => (!authLoading && !user) ? nav('/auth?mode=signup') : window.scrollTo({ top: 0, behavior: 'smooth' })} />

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
