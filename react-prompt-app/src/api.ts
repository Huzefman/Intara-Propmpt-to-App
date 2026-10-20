// API helpers — 25 lines, typed, guarded
import { apiFetch } from './api/client'

export type GenerateRes = { tables: { name: string; fields: { name: string; type: string }[] }[] }

export async function generateSchema(prompt: string): Promise<GenerateRes> {
  const res = await apiFetch('/api/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  })
  if (!res.ok) throw new Error(`generate failed ${res.status}`)
  return res.json()
}

export async function askRag(question: string): Promise<{ answer: string; cites: string[] }> {
  const res = await apiFetch('/api/rag', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  if (!res.ok) throw new Error(`rag failed ${res.status}`)
  return res.json()
}
