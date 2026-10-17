/**
 * Static demo mode (portfolio packaging): VITE_DEMO=1 at build time makes the
 * Studio run with zero backend — the Templates gallery serves the 10 gold
 * specs bundled from packages/spec/exemplars/ and every app runs fully in the
 * browser (Dexie adapter, no LLM). Used for the public Vercel link.
 */
export const DEMO = import.meta.env.VITE_DEMO === '1'

export const GITHUB_URL = 'https://github.com/Huzefman/intara'
