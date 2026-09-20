import { useEffect, useState } from 'react'
import { getWish, Wish } from '../api/client'

export function useWish(id: string | undefined) {
  const [wish, setWish] = useState<Wish | null>(null)
  const [loading, setLoading] = useState(!!id)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    setLoading(true)
    setErr(null)
    getWish(id).then((w) => { if (!cancelled) setWish(w) })
      .catch((e) => { if (!cancelled) setErr(e.message) })
      .finally(() => { if (!cancelled) setLoading(false) })

    // poll if weaving — backoff + timeout to avoid hammering free-tier
    let attempts = 0
    const iv = setInterval(async () => {
      attempts += 1
      if (attempts > 30) { clearInterval(iv); return } // 60s max
      try {
        const w = await getWish(id)
        if (!cancelled) {
          setWish(w)
          if (w.status !== 'weaving') clearInterval(iv)
        }
      } catch {}
    }, 2000)
    return () => { cancelled = true; clearInterval(iv) }
  }, [id])

  return { wish, loading, err, setWish }
}
