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

// Intara wishes
export type Wish = {
  id: string
  prompt: string
  prd: any
  artifacts: any
  status: 'weaving' | 'ready' | 'failed'
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
