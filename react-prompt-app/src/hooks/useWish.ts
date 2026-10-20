import { useEffect, useState } from 'react'
import { apiFetch, getWish, Wish } from '../api/client'

export function useWish(id: string | undefined) {
  const [wish, setWish] = useState<Wish | null>(null)
  const [loading, setLoading] = useState(!!id)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    setLoading(true)
    setBusy(false)
    setErr(null)
    // Bounded first load: if the server is mid-build its loop can be slow —
    // say so instead of spinning silently. Polling below keeps retrying.
    const ctrl = new AbortController()
    const busyTimer = setTimeout(() => { if (!cancelled) setBusy(true) }, 8000)
    apiFetch(`/api/wish/${id}`, { signal: ctrl.signal })
      .then((res) => {
        if (!res.ok) throw new Error(`get wish failed ${res.status}`)
        return res.json()
      })
      .then((w) => { if (!cancelled) setWish(w) })
      .catch((e) => {
        if (cancelled || e?.name === 'AbortError') return
        if (!cancelled) setErr(e.message)
      })
      .finally(() => { if (!cancelled) { setLoading(false); setBusy(false) } clearTimeout(busyTimer) })

    // poll while the wish is still moving (weaving / planning / building) —
    // backoff + timeout to avoid hammering free-tier
    let attempts = 0
    const iv = setInterval(async () => {
      attempts += 1
      if (attempts > 90) { clearInterval(iv); return } // 3min max (covers slow free-pool plans)
      try {
        const w = await getWish(id)
        if (!cancelled) {
          setWish(w)
          setLoading(false)
          setBusy(false)
          if (w.status === 'ready' || w.status === 'failed' || w.status === 'awaiting_approval') clearInterval(iv)
        }
      } catch {}
    }, 2000)
    return () => { cancelled = true; clearInterval(iv); clearTimeout(busyTimer); try { ctrl.abort() } catch {} }
  }, [id])

  return { wish, loading, busy, err, setWish }
}
