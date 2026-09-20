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

export async function createPlan(prompt: string): Promise<Wish> {
  const controller = new AbortController()
  const t = setTimeout(() => controller.abort(), 35000)
  try {
    const res = await fetch('/api/wish/plan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt }), signal: controller.signal })
    if (!res.ok) {
      const txt = await res.text().catch(() => '')
      throw new Error(`plan failed ${res.status} ${txt}`)
    }
    return res.json()
  } finally { clearTimeout(t) }
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
