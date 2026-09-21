import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { answerClarify, approvePlan, createPlan, getSuggest, regenerateWish, type Suggestion, type Wish } from '../api/client'

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
          <p className="thread-q-title">{i + 1}. {q.q}</p>
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
        <div className="thread-graph">
          {graph.map((n: any, i: number) => (
            <span key={n.id || i} className="thread-graph-node" title={n.promptHint || n.kind}>{n.kind}{n.ref ? `: ${n.ref}` : ''}</span>
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
  return (
    <div>
      <p style={{ marginTop: 0 }}><strong>✦ Forged {prd.appName || 'your app'} — here's what I did:</strong></p>
      <ul className="thread-did">
        <li>Shaped <strong>{tables.length}</strong> tables{tables.length > 0 && ` (${tables.map((t: any) => t.name).join(', ')})`} with relations</li>
        <li>Built <strong>{pages.length}</strong> pages + <strong>{apis.length}</strong> API endpoints</li>
        <li>Trial runs on mock data in your browser — swap in Supabase anytime</li>
        <li>Runnable zip is packed and ready to download</li>
      </ul>
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
          <AgentBubble><p>Refining your wish into a plan…</p></AgentBubble>
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
    </div>
  )
}
