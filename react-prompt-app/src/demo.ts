/**
 * Static demo mode: VITE_DEMO=1 at build time makes the Studio run with zero
 * backend — the Templates gallery serves the 10 curated specs bundled from
 * packages/spec/exemplars/ and every app runs fully in the browser (Dexie
 * adapter, no LLM). Used for the public Vercel build.
 */
export const DEMO = import.meta.env.VITE_DEMO === '1'

export const GITHUB_URL = 'https://github.com/Huzefman/Intara-Propmpt-to-App'
