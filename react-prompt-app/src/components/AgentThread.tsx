import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { answerClarify, applyIterate, approvePlan, createPlan, getChat, getSuggest, postChat, previewIterate, regenerateWish, retryStep, revertIterate, type ChatAction, type ChatMessage, type IterPreview, type Suggestion, type Wish } from '../api/client'

/* ---------- small pieces ---------- */

function UserBubble({ prompt }: { prompt: string }) {
  return (
    <div className="thread-msg thread-user">
      <div className="thread-avatar" aria-hidden="true">you</div>
      <div className="thread-bubble glass">{prompt}</div>
    </div>
  )
}

function AgentBubble({ children }: { children: ReactNode }) {
  return (
    <div className="thread-msg thread-agent">
      <div className="thread-avatar thread-avatar-agent" aria-hidden="true">✦</div>
      <div className="thread-bubble glass">{children}</div>
    </div>
  )
}

function ScoreCard({ score, mock }: { score: number; mock: boolean }) {
  return (
    <div>
      <div className="thread-score-row">
        <strong>Wish clarity</strong>
        <span className={`pill ${score >= 70 ? 'pill-good' : 'pill-warn'}`}>{score}%</span>
      </div>
      <div className="thread-score-bar" role="progressbar" aria-valuenow={score} aria-valuemin={0} aria-valuemax={100} aria-label="Wish clarity score">
        <span style={{ width: `${score}%` }} />
      </div>
      <p className="muted" style={{ margin: '8px 0 0' }}>
        {score >= 70
          ? 'Sharp enough to plan straight away.'
          : 'A little blurry — two quick questions will focus it.'}
        {mock && ' Template check (LLM busy) — answers still shape the plan.'}
      </p>
    </div>
  )
}

function ClarifyCards({ questions, answers, onPick, submitting, onSubmit, onSkip, err }: {
  questions: any[]; answers: Record<string, string>; onPick: (qid: string, label: string) => void
  submitting: boolean; onSubmit: () => void; onSkip: () => void; err: string | null
}) {
  const answered = Object.keys(answers).length
  return (
    <div>
      <p style={{ marginTop: 0 }}><strong>Two quick questions so I build the right thing:</strong></p>
      {questions.map((q, i) => (
        <div key={q.id || i} className="thread-q">
          <p className="thread-q-title"><span className="thread-q-num">{String(i + 1).padStart(2, '0')}</span>{q.q}</p>
          <div className="thread-opts">
            {(q.options || []).map((o: any) => (
              <button
                key={o.label}
                className={`thread-opt ${answers[q.id] === o.label ? 'selected' : ''}`}
                onClick={() => onPick(q.id, o.label)}
                aria-pressed={answers[q.id] === o.label}
              >
                <strong>{o.label}</strong>
                {o.desc && <span className="muted">{o.desc}</span>}
              </button>
            ))}
          </div>
        </div>
      ))}
      {err && <p className="error" role="alert">{err}</p>}
      <div className="thread-actions">
        <button className="btn-primary" onClick={onSubmit} disabled={submitting}>
          {submitting ? 'Focusing your wish…' : `Continue${answered ? ` (${answered} answered)` : ''} →`}
        </button>
        <button className="btn-ghost" onClick={onSkip} disabled={submitting}>Build without answering →</button>
      </div>
    </div>
  )
}

const PLAN_PHASES = [
  { id: 'clarifying', label: 'Clarifying' },
  { id: 'drafting_tables', label: 'Tables' },
  { id: 'drafting_pages', label: 'Pages' },
] as const

function PlanProgress({ phase, label }: { phase?: string | null; label?: string | null }) {
  const order = PLAN_PHASES.map((p) => p.id)
  const activeIdx = phase ? order.indexOf(phase as (typeof order)[number]) : 0
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }} aria-label="Plan progress">
        {PLAN_PHASES.map((p, i) => {
          const done = activeIdx > i
          const active = activeIdx === i
          return (
            <span key={p.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <span style={{
                padding: '6px 10px', borderRadius: 999, fontSize: 11, fontWeight: active ? 600 : 500,
                background: done ? 'rgba(16,185,129,0.12)' : active ? 'rgba(139,92,246,0.16)' : 'rgba(255,255,255,0.04)',
                border: `1px solid ${done ? 'rgba(16,185,129,0.22)' : active ? 'rgba(139,92,246,0.32)' : 'rgba(255,255,255,0.06)'}`,
                color: done ? '#10B981' : active ? 'var(--intara-nebula-light)' : 'var(--intara-faint)',
                animation: active ? 'pulse 1.2s ease-in-out infinite' : 'none',
                whiteSpace: 'nowrap',
              }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: done ? '#10B981' : active ? '#8B5CF6' : 'var(--intara-dim)', display: 'inline-block', marginRight: 6, verticalAlign: 'middle' }} />
                {p.label}
              </span>
              {i < PLAN_PHASES.length - 1 && <span style={{ color: 'var(--intara-dim)', fontSize: 10 }}>→</span>}
            </span>
          )
        })}
      </div>
      {(label || activeIdx >= 0) && (
        <div style={{ fontSize: 11.5, color: 'var(--intara-faint)', marginTop: 8 }}>
          <span className="chat-shimmer" aria-label="Planning in progress">✦</span> {label || 'Warming up the forge…'}
        </div>
      )}
      <style>{`@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.7; } }`}</style>
    </div>
  )
}

function phaseChips(graph: any[]): { label: string }[] {  const tables = graph.filter(n => n.kind === 'backend_table').length
  const pages = graph.filter(n => n.kind === 'frontend_page').length
  const chips = [{ label: '01 wish' }, { label: '02 schema' }]
  if (tables) chips.push({ label: `03 ${tables} table${tables === 1 ? '' : 's'}` })
  if (pages) chips.push({ label: `0${chips.length + 1} ${pages} page${pages === 1 ? '' : 's'}` })
  chips.push({ label: `0${chips.length + 1} ship` })
  return chips
}

function PlanSummary({ prd, onApprove, approving, err }: { prd: any; onApprove: () => void; approving: boolean; err: string | null }) {
  const tables = prd.tables || []
  const pages = prd.pages || []
  const apis = prd.apis || []
  const graph = prd.buildGraph || []
  const redrafted = prd._meta?.clarify?.redrafted
  return (
    <div>
      <p style={{ marginTop: 0 }}><strong>Plan ready — {prd.appName || 'your app'}</strong></p>
      {prd.tagline && <p className="muted">{prd.tagline}</p>}
      {redrafted && redrafted !== prd.tagline && (
        <p className="thread-redraft">✦ Focused wish: {redrafted}</p>
      )}
      <div className="thread-counts">
        <span className="pill">{tables.length} tables</span>
        <span className="pill">{pages.length} pages</span>
        <span className="pill">{apis.length} endpoints</span>
        {prd.auth && <span className="pill">auth</span>}
      </div>
      {tables.length > 0 && <p className="muted">Data: {tables.map((t: any) => t.name).join(' · ')}</p>}
      {graph.length > 0 && (
        <div className="thread-graph" aria-label="Build phases">
          {phaseChips(graph).map((ph, i, arr) => (
            <span key={ph.label} className="thread-phase">
              <span className="thread-graph-node">{ph.label}</span>
              {i < arr.length - 1 && <span className="thread-phase-sep" aria-hidden="true">›</span>}
            </span>
          ))}
        </div>
      )}
      {err && <p className="error" role="alert">{err}</p>}
      <div className="thread-actions">
        <button className="btn-primary" onClick={onApprove} disabled={approving}>
          {approving ? 'Igniting build…' : 'Approve plan — build it ✦'}
        </button>
      </div>
      <p className="muted">Sequential staged build. You can retry any failed step.</p>
    </div>
  )
}

function WhatIDid({ prd }: { prd: any }) {
  const tables = prd.tables || []
  const pages = prd.pages || []
  const apis = prd.apis || []
  const items = tables.length + pages.length + apis.length
  return (
    <div>
      <p style={{ marginTop: 0 }}><strong>✦ Forged {prd.appName || 'your app'} — here's what I did:</strong></p>
      <ul className="thread-did">
        <li>Shaped <strong>{tables.length}</strong> tables{tables.length > 0 && ` (${tables.map((t: any) => t.name).join(', ')})`} with relations</li>
        <li>Built <strong>{pages.length}</strong> pages + <strong>{apis.length}</strong> API endpoints</li>
        <li>Trial runs on mock data in your browser — swap in Supabase anytime</li>
        <li>Runnable zip is packed and ready to download</li>
      </ul>
      <button className="thread-files-row" onClick={() => window.dispatchEvent(new CustomEvent('studio:code'))} title="Open the Code tab in the preview pane">
        <span><strong>Files</strong></span>
        <span className="muted mono">Version 1 · {items} items ›</span>
      </button>
    </div>
  )
}

function ActionsRow({ wish, onChanged }: { wish: Wish; onChanged: () => void }) {
  const [busy, setBusy] = useState(false)
  async function onZip() {
    const artifacts = wish.artifacts || {}
    if (!artifacts.schema) return
    setBusy(true)
    try {
      const { buildWishZip, downloadBlob } = await import('../lib/zip')
      const { blob, filename } = await buildWishZip(artifacts, wish.prd?.appName || 'Intara Wish')
      downloadBlob(blob, filename)
    } finally { setBusy(false) }
  }
  async function onRegen() {
    setBusy(true)
    try { await regenerateWish(wish.id); onChanged() } catch { /* surfaced on refresh */ } finally { setBusy(false) }
  }
  return (
    <div className="thread-actions">
      <button className="btn-primary btn-sm" onClick={onZip} disabled={busy || !wish.artifacts?.schema}>Download zip</button>
      <button className="btn-ghost btn-sm" onClick={() => navigator.clipboard.writeText(window.location.href)}>Copy link</button>
      <button className="btn-ghost btn-sm" onClick={onRegen} disabled={busy}>Regenerate</button>
    </div>
  )
}

function SuggestChips({ wish }: { wish: Wish }) {
  const nav = useNavigate()
  const [items, setItems] = useState<Suggestion[] | null>(null)
  const [forking, setForking] = useState<string | null>(null)
  useEffect(() => {
    let live = true
    getSuggest(wish.id).then((s) => { if (live) setItems(s) }).catch(() => { if (live) setItems([]) })
    return () => { live = false }
  }, [wish.id])
  if (!items || items.length === 0) return null
  async function onFork(s: Suggestion) {
    setForking(s.label)
    try {
      const next = await createPlan(wish.prompt + s.prompt_suffix)
      nav(`/wish/${next.id}`)
    } finally { setForking(null) }
  }
  return (
    <div>
      <p style={{ marginTop: 0 }}><strong>Suggested next steps:</strong></p>
      <div className="thread-suggest">
        {items.map((s) => (
          <button key={s.label} className="thread-suggest-chip" onClick={() => onFork(s)} disabled={!!forking} title={s.detail}>
            {forking === s.label ? 'Forking…' : `+ ${s.label}`}
          </button>
        ))}
      </div>
    </div>
  )
}

/* ---------- wish-scoped chat (Q&A + action chips, persisted, 20/day/IP) ---------- */

type ChatTurn = ChatMessage & { actions?: ChatAction[]; pending?: boolean }

function ChatThread({ wish, onChanged }: { wish: Wish; onChanged: () => void }) {
  const nav = useNavigate()
  const [messages, setMessages] = useState<ChatTurn[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [lastFailed, setLastFailed] = useState<string | null>(null)
  const [chatsLeft, setChatsLeft] = useState<number | null>(null)
  const [acting, setActing] = useState<string | null>(null)
  const [pendingFix, setPendingFix] = useState<IterPreview | null>(null)
  const [appliedFix, setAppliedFix] = useState<{ iid: string; summary: string } | null>(null)
  const [fixBusy, setFixBusy] = useState(false)
  const bottomRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    let live = true
    getChat(wish.id).then((m) => { if (live) setMessages(m) }).catch(() => { if (live) setMessages([]) })
    return () => { live = false }
  }, [wish.id])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, sending, pendingFix, appliedFix])

  async function send(text?: string) {
    const msg = (text ?? input).trim()
    if (!msg || sending) return
    if (msg.length > 1000) { setErr('Message too long (max 1000 characters).'); return }
    setSending(true)
    setErr(null)
    setLastFailed(null)
    setMessages((prev) => [...prev, { role: 'user', content: msg }, { role: 'agent', content: '', pending: true }])
    if (text == null) setInput('')
    try {
      const res = await postChat(wish.id, msg)
      setMessages((prev) => {
        const next = [...prev]
        // drop trailing pending placeholder
        for (let i = next.length - 1; i >= 0; i--) {
          if (next[i].pending) { next.splice(i, 1); break }
        }
        next.push({ role: 'agent', content: res.reply, actions: res.actions })
        return next
      })
      setChatsLeft((prev) => (prev === null ? 19 : Math.max(0, prev - 1)))
    } catch (e: any) {
      setMessages((prev) => prev.filter((m) => !m.pending))
      if (e?.status === 429) {
        setChatsLeft(0)
        setErr('Chat stardust spent — 20 chats per day per IP (builds share the same free pool). Back tomorrow.')
      } else {
        setErr(e?.message || 'Could not send — retry shortly.')
      }
      setLastFailed(msg)
    } finally {
      setSending(false)
    }
  }

  function onKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey || !e.shiftKey)) {
      e.preventDefault()
      void send()
    }
  }

  async function onAction(a: ChatAction) {
    if (acting || fixBusy) return
    if (a.kind === 'fix') { await onFixPreview(a); return }
    setActing(a.label)
    try {
      if (a.kind === 'retry' && a.stepId) {
        await retryStep(wish.id, a.stepId)
        onChanged()
      } else if (a.kind === 'fork' && a.suffix) {
        const next = await createPlan(wish.prompt + a.suffix)
        nav(`/wish/${next.id}`)
      }
    } catch (e: any) {
      setErr(e?.message || 'Action failed — retry shortly.')
    } finally {
      setActing(null)
    }
  }

  async function onFixPreview(a: ChatAction) {
    const lastUser = [...messages].reverse().find((m) => m.role === 'user' && !m.pending)
    const instruction = (lastUser?.content || '').replace(/^\[iterate\]\s*/, '').trim()
    if (!instruction) { setErr('Ask for the change first (e.g. "fix the Tasks page header"), then hit Apply this fix.'); return }
    setFixBusy(true)
    setErr(null)
    setPendingFix(null)
    try {
      const prev = await previewIterate(wish.id, instruction, a.stepId)
      setPendingFix(prev)
      setChatsLeft((prevLeft) => (prevLeft === null ? 19 : Math.max(0, prevLeft - 1)))
    } catch (e: any) {
      if (e?.status === 429) {
        setChatsLeft(0)
        setErr('Chat stardust spent — 20 chats per day per IP (builds share the same free pool). Back tomorrow.')
      } else {
        setErr(e?.message || 'Could not preview the fix — retry shortly.')
      }
    } finally {
      setFixBusy(false)
    }
  }

  async function onFixAccept() {
    if (!pendingFix || fixBusy) return
    setFixBusy(true)
    try {
      await applyIterate(wish.id, pendingFix.iteration_id)
      setAppliedFix({ iid: pendingFix.iteration_id, summary: pendingFix.summary })
      setPendingFix(null)
      onChanged()
    } catch (e: any) {
      setErr(e?.message || 'Apply failed — retry shortly.')
    } finally {
      setFixBusy(false)
    }
  }

  async function onFixRevert() {
    if (!appliedFix || fixBusy) return
    setFixBusy(true)
    try {
      await revertIterate(wish.id, appliedFix.iid)
      setAppliedFix(null)
      onChanged()
    } catch (e: any) {
      setErr(e?.message || 'Revert failed — retry shortly.')
    } finally {
      setFixBusy(false)
    }
  }

  return (
    <div className="chat-thread">
      {messages.map((m, i) =>
        m.role === 'user' ? (
          <UserBubble key={i} prompt={m.content} />
        ) : m.pending ? (
          <AgentBubble key={i}><span className="chat-shimmer" aria-label="Intara is thinking">✦ thinking…</span></AgentBubble>
        ) : (
          <AgentBubble key={i}>
            <div style={{ whiteSpace: 'pre-wrap' }}>{m.content}</div>
            {m.actions && m.actions.length > 0 && (
              <div className="thread-suggest" style={{ marginTop: 10 }}>
                {m.actions.map((a) => (
                  <button
                    key={a.label}
                    className="thread-suggest-chip"
                    disabled={!!acting || fixBusy}
                    onClick={() => onAction(a)}
                    title={a.kind === 'fix' ? 'Preview a diff-first code change' : a.kind === 'retry' ? 'Retry via existing endpoint' : 'Fork via existing plan endpoint'}
                  >
                    {acting === a.label || (fixBusy && a.kind === 'fix') ? 'Working…' : a.label}
                  </button>
                ))}
              </div>
            )}
          </AgentBubble>
        ),
      )}
      {err && (
        <AgentBubble>
          <p className="error" role="alert" style={{ marginTop: 0 }}>{err}</p>
          {lastFailed && (
            <div className="thread-actions">
              <button className="btn-ghost btn-sm" onClick={() => send(lastFailed)} disabled={sending}>
                {sending ? 'Retrying…' : 'Retry send'}
              </button>
            </div>
          )}
        </AgentBubble>
      )}
      {pendingFix && (
        <AgentBubble>
          <p style={{ marginTop: 0 }}><strong>✦ Proposed change — {pendingFix.step_id}</strong></p>
          <p className="muted">{pendingFix.summary}</p>
          <div className="diff-card">
            {pendingFix.files.map((f) => (
              <details key={f.path} className="diff-file">
                <summary>
                  <span className="mono">{f.path}</span>
                  <span className="muted"> {f.before.split('\n').length} → {f.after.split('\n').length} lines</span>
                </summary>
                <div className="diff-panes">
                  <div>
                    <div className="diff-pane-label">Before</div>
                    <pre className="diff-pane">{f.before.slice(0, 4000)}</pre>
                  </div>
                  <div>
                    <div className="diff-pane-label">After</div>
                    <pre className="diff-pane diff-after">{f.after.slice(0, 4000)}</pre>
                  </div>
                </div>
              </details>
            ))}
          </div>
          <div className="thread-actions">
            <button className="btn-primary btn-sm" onClick={onFixAccept} disabled={fixBusy}>
              {fixBusy ? 'Applying…' : 'Accept — apply to app'}
            </button>
            <button className="btn-ghost btn-sm" onClick={() => setPendingFix(null)} disabled={fixBusy}>Discard</button>
          </div>
          <p className="muted">Nothing changes until you Accept. Wiring re-ran with the edit.</p>
        </AgentBubble>
      )}
      {appliedFix && (
        <AgentBubble>
          <p style={{ marginTop: 0 }}><strong>✓ Applied</strong> <span className="muted">{appliedFix.summary}</span></p>
          <div className="thread-actions">
            <button className="btn-ghost btn-sm" onClick={onFixRevert} disabled={fixBusy}>
              {fixBusy ? 'Reverting…' : 'Revert this change'}
            </button>
          </div>
        </AgentBubble>
      )}
      {fixBusy && !pendingFix && !appliedFix && (
        <AgentBubble><span className="chat-shimmer" aria-label="Preparing fix preview">✦ preparing fix preview… (up to ~1 min on the free pool)</span></AgentBubble>
      )}
      <div ref={bottomRef} />
      <div className="chat-composer glass">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          rows={1}
          maxLength={1000}
          placeholder="Ask about this app — plan, steps, errors…"
          aria-label="Ask about this app"
          disabled={sending}
        />
        <button className="btn-primary btn-sm" onClick={() => send()} disabled={sending || !input.trim()}>
          {sending ? 'Sending…' : 'Send'}
        </button>
      </div>
      <div className="chat-day-budget" aria-live="polite">
        {chatsLeft === null ? '20 chats/day · shared free pool' : chatsLeft > 0 ? `${chatsLeft} chats left today` : '0 chats left today'}
      </div>
    </div>
  )
}

/* ---------- thread ---------- */

export function AgentThread({ wish, onChanged, buildView }: { wish: Wish; onChanged: () => void; buildView?: ReactNode }) {
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)
  const [approving, setApproving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const prd = wish.prd || {}
  const clarify = prd.clarify || prd._meta?.clarify || null
  const mock = prd._meta?.source === 'mock'

  async function submit(answersToSend: Record<string, string>) {
    setSubmitting(true)
    setErr(null)
    try {
      const updated = await answerClarify(wish.id, answersToSend)
      void updated
      onChanged()
    } catch (e: any) {
      setErr(e.message || 'Could not send answers — retry shortly.')
    } finally { setSubmitting(false) }
  }

  async function approve() {
    setApproving(true)
    setErr(null)
    try {
      await approvePlan(wish.id)
      onChanged()
    } catch (e: any) {
      setErr(e.message || 'Approve failed — retry shortly.')
    } finally { setApproving(false) }
  }

  return (
    <div className="thread" aria-live="polite">
      <UserBubble prompt={wish.prompt} />

      {clarify && typeof clarify.score === 'number' && (
        <AgentBubble><ScoreCard score={clarify.score} mock={mock || clarify._meta?.source === 'mock'} /></AgentBubble>
      )}

      {wish.status === 'planning' && (
        clarify?.questions?.length ? (
          <AgentBubble>
            <PlanProgress phase={wish.artifacts?.plan_phase?.phase} label={wish.artifacts?.plan_phase?.label} />
            <ClarifyCards
              questions={clarify.questions}
              answers={answers}
              onPick={(qid, label) => setAnswers(a => ({ ...a, [qid]: label }))}
              submitting={submitting}
              onSubmit={() => submit(answers)}
              onSkip={() => submit({})}
              err={err}
            />
          </AgentBubble>
        ) : (
          <AgentBubble>
            <PlanProgress phase={wish.artifacts?.plan_phase?.phase} label={wish.artifacts?.plan_phase?.label} />
            <p>Refining your wish into a plan…</p>
          </AgentBubble>
        )
      )}

      {wish.status === 'awaiting_approval' && (
        <AgentBubble><PlanSummary prd={prd} onApprove={approve} approving={approving} err={err} /></AgentBubble>
      )}

      {(wish.status === 'approved' || wish.status === 'building') && (
        <AgentBubble>
          <p style={{ marginTop: 0 }}><strong>Building now — watch each step land:</strong></p>
          {buildView}
        </AgentBubble>
      )}

      {wish.status === 'ready' && (
        <>
          <AgentBubble><WhatIDid prd={prd} /></AgentBubble>
          <AgentBubble><ActionsRow wish={wish} onChanged={onChanged} /></AgentBubble>
          <AgentBubble><SuggestChips wish={wish} /></AgentBubble>
        </>
      )}

      {wish.status === 'failed' && (
        <AgentBubble>
          <p style={{ marginTop: 0 }}><strong>The forge stalled.</strong> Quota or a bad step — your plan is safe.</p>
          {err && <p className="error" role="alert">{err}</p>}
          <div className="thread-actions">
            <button className="btn-primary btn-sm" onClick={approve} disabled={approving}>{approving ? 'Retrying…' : 'Retry build'}</button>
          </div>
        </AgentBubble>
      )}

      {wish.status === 'weaving' && (
        <AgentBubble><p>Weaving your wish one-shot… the trial appears in the preview pane shortly.</p></AgentBubble>
      )}

      <AgentBubble><ChatThread wish={wish} onChanged={onChanged} /></AgentBubble>
    </div>
  )
}
