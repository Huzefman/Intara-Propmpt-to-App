// Supabase client — 15 lines you type first in interview
// npm install @supabase/supabase-js
import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL as string
const key = import.meta.env.VITE_SUPABASE_ANON_KEY as string

if (!url || !key) {
  console.warn('Missing VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY — using demo mode (Intara MEM store, no auth)')
}

export const supabase = createClient(url || 'https://demo.supabase.co', key || 'demo-key')

export const isSupabaseDemo = !url || !key || url.includes('demo.supabase.co')

// Table: schemas(id, prompt, tables jsonb, created_at)
// Usage: supabase.from('schemas').insert({prompt, tables}).select()
