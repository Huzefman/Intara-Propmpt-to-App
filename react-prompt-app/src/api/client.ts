// Intara API client — wraps /api/wish + /api/rag + legacy /api/generate
export type GenerateRes = { tables: { name: string; fields: { name: string; type: string }[] }[] }

export async function generateSchema(prompt: string): Promise<GenerateRes> {
  const res = await fetch('/api/generate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt }) })
  if (!res.ok) throw new Error(`generate failed ${res.status}`)
  return res.json()
}

export async function askRag(question: string): Promise<{ answer: string; cites: string[] }> {
  const res = await fetch('/api/rag', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question }) })
  if (!res.ok) throw new Error(`rag failed ${res.status}`)
  return res.json()
}

// Intara wishes — staged sequential + one-shot legacy
export type WishStatus = 'planning' | 'awaiting_approval' | 'approved' | 'building' | 'weaving' | 'ready' | 'failed'
export type Wish = {
  id: string
  prompt: string
  prd: any
  artifacts: any
  status: WishStatus
  created_at: string
}

export async function createWish(prompt: string): Promise<Wish> {
  const res = await fetch('/api/wish', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt }) })
  if (!res.ok) {
    const t = await res.text().catch(() => '')
    throw new Error(`wish failed ${res.status} ${t}`)
  }
  return res.json()
}

export class PlanAbortedError extends Error {
  prompt: string
  constructor(prompt: string) {
    super('Still weaving — the wish takes longer than usual. It is likely safe: check Constellation or retry and you will land straight in the build chat.')
    this.name = 'PlanAbortedError'
    this.prompt = prompt
  }
}

export async function createPlan(prompt: string): Promise<Wish> {
  // Server returns a shell instantly (202) and plans in background, so this
  // timer is a safety net only — it must never surface a raw AbortError.
  const controller = new AbortController()
  const t = setTimeout(() => controller.abort(), 150000)
  try {
    const res = await fetch('/api/wish/plan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt }), signal: controller.signal })
    if (!res.ok) {
      const txt = await res.text().catch(() => '')
      throw new Error(`plan failed ${res.status} ${txt}`)
    }
    return res.json()
  } catch (e: any) {
    if (e?.name === 'AbortError') throw new PlanAbortedError(prompt)
    throw e
  } finally { clearTimeout(t) }
}

/** After an abort/timeout: find a just-created wish for the same prompt (<3 min old). */
export async function reconcileWish(prompt: string): Promise<Wish | null> {
  try {
    const all = await listWishes()
    const now = Date.now()
    const mine = all
      .filter((w) => w.prompt === prompt)
      .filter((w) => {
        const t = Date.parse(w.created_at)
        return Number.isFinite(t) && now - t < 3 * 60 * 1000
      })
      .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
    return mine[0] ?? null
  } catch {
    return null
  }
}

export async function patchPlan(id: string, prd: any): Promise<Wish> {
  const res = await fetch(`/api/wish/${id}/plan`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prd }) })
  if (!res.ok) throw new Error(`patch plan failed ${res.status}`)
  return res.json()
}

export async function approvePlan(id: string): Promise<{ok:boolean}> {
  const res = await fetch(`/api/wish/${id}/approve`, { method: 'POST' })
  if (!res.ok) throw new Error(`approve failed ${res.status}`)
  return res.json()
}

export async function answerClarify(id: string, answers: Record<string,string>): Promise<Wish> {
  const res = await fetch(`/api/wish/${id}/answer`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ answers }) })
  if (!res.ok) {
    const t = await res.text().catch(() => '')
    throw new Error(`answer failed ${res.status} ${t}`)
  }
  return res.json()
}

export type Suggestion = { label: string; detail: string; prompt_suffix: string }

export async function getSuggest(id: string): Promise<Suggestion[]> {
  const res = await fetch(`/api/wish/${id}/suggest`)
  if (!res.ok) throw new Error(`suggest failed ${res.status}`)
  const data = await res.json()
  return data.suggestions ?? []
}

export function streamBuild(id: string, onEvent: (ev:any)=>void): () => void {
  const es = new EventSource(`/api/wish/${id}/stream`)
  es.onmessage = (e) => {
    try { onEvent(JSON.parse(e.data)) } catch { onEvent({event:'message', data:e.data}) }
  }
  es.onerror = () => { /* will fallback to polling */ }
  return () => es.close()
}

export async function retryStep(id: string, stepId: string): Promise<any> {
  const res = await fetch(`/api/wish/${id}/retry`, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({stepId}) })
  if (!res.ok) throw new Error(`retry failed ${res.status}`)
  return res.json()
}

export async function getWish(id: string): Promise<Wish> {
  const res = await fetch(`/api/wish/${id}`)
  if (!res.ok) throw new Error(`get wish failed ${res.status}`)
  return res.json()
}

export async function listWishes(): Promise<Wish[]> {
  const res = await fetch('/api/wishes')
  if (!res.ok) throw new Error(`list wishes failed ${res.status}`)
  return res.json()
}

export async function regenerateWish(id: string): Promise<Wish> {
  const res = await fetch(`/api/wish/${id}/regenerate`, { method: 'POST' })
  if (!res.ok) throw new Error(`regenerate failed ${res.status}`)
  return res.json()
}

// Wish-scoped custom chat (Q&A + action chips), persisted history, 20/day per IP
export type ChatMessage = { role: 'user' | 'agent'; content: string; created_at?: string }
export type ChatAction = { label: string; kind: 'retry' | 'fork' | 'fix'; stepId?: string; suffix?: string }

function apiError(path: string, res: Response, body: string): Error {
  let msg = body
  try {
    const j = JSON.parse(body)
    if (typeof j?.detail === 'string' && j.detail) msg = j.detail
  } catch { /* keep raw body */ }
  return new Error(msg || `${path} failed ${res.status}`)
}

export async function getChat(id: string): Promise<ChatMessage[]> {
  const res = await fetch(`/api/wish/${id}/chat`)
  if (!res.ok) throw apiError('chat history', res, await res.text().catch(() => ''))
  const data = await res.json()
  return data.messages ?? []
}

export async function postChat(id: string, message: string): Promise<{ reply: string; actions: ChatAction[]; degraded?: boolean }> {
  const res = await fetch(`/api/wish/${id}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })
  if (!res.ok) {
    const err: any = apiError('chat', res, await res.text().catch(() => ''))
    err.status = res.status
    throw err
  }
  return res.json()
}

// Chat-driven rewrites (diff-first, one-click revert). Previews share the 20/day chat cap.
export type IterFile = { path: string; before: string; after: string; area?: string }
export type IterPreview = { iteration_id: string; step_id: string; files: IterFile[]; summary: string }

export async function previewIterate(id: string, instruction: string, stepId?: string): Promise<IterPreview> {
  const res = await fetch(`/api/wish/${id}/iterate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ instruction, stepId: stepId ?? null }),
  })
  if (!res.ok) {
    const err: any = apiError('iterate', res, await res.text().catch(() => ''))
    err.status = res.status
    throw err
  }
  return res.json()
}

export async function applyIterate(id: string, iterId: string): Promise<Wish> {
  const res = await fetch(`/api/wish/${id}/iterate/${iterId}/apply`, { method: 'POST' })
  if (!res.ok) throw apiError('apply', res, await res.text().catch(() => ''))
  return res.json()
}

export async function revertIterate(id: string, iterId: string): Promise<Wish> {
  const res = await fetch(`/api/wish/${id}/iterate/${iterId}/revert`, { method: 'POST' })
  if (!res.ok) throw apiError('revert', res, await res.text().catch(() => ''))
  return res.json()
}

// v2 runs (spec pipeline): start/status/events/approve/chat-patch
export async function startRun(wish: string, appName?: string, wishId?: string): Promise<{ ok: boolean; run_id: string; project_id: string }> {
  const res = await fetch('/api/runs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ wish, kind: 'build', app_name: appName || 'App', wish_id: wishId || null }) })
  if (!res.ok) throw new Error(`start run failed ${res.status}`)
  return res.json()
}

export async function getRun(runId: string): Promise<any> {
  const res = await fetch(`/api/runs/${runId}`)
  if (!res.ok) throw new Error(`get run failed ${res.status}`)
  return res.json()
}

export function streamRun(runId: string, onEvent: (ev: any) => void): () => void {
  const es = new EventSource(`/api/runs/${runId}/events`)
  es.onmessage = (e) => {
    try { onEvent(JSON.parse(e.data)) } catch { /* heartbeat */ }
  }
  es.onerror = () => { /* polling fallback covers */ }
  return () => es.close()
}

export async function approveRun(runId: string, by?: string): Promise<{ ok: boolean; version_id: string }> {
  const res = await fetch(`/api/runs/${runId}/approve`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ by: by || 'owner' }) })
  if (!res.ok) throw new Error(`approve failed ${res.status}`)
  return res.json()
}

export async function chatRun(runId: string, instruction: string): Promise<{ ok: boolean; version_id: string; summary: string; spec: any }> {
  const res = await fetch(`/api/runs/${runId}/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ instruction }) })
  if (!res.ok) throw new Error(`chat patch failed ${res.status}`)
  return res.json()
}

export async function patchRun(runId: string, ops: any[], summary: string, baseVersion?: string): Promise<{ ok: boolean; version_id: string; summary: string; spec: any }> {
  const res = await fetch(`/api/runs/${runId}/patch`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ops, summary, base_version: baseVersion || null }) })
  if (!res.ok) {
    const t = await res.text().catch(() => '')
    throw new Error(`patch failed ${res.status} ${t.slice(0, 200)}`)
  }
  return res.json()
}
