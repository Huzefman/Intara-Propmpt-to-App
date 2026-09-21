import { useEffect, useRef } from 'react'

/**
 * useReveal — IntersectionObserver-driven scroll reveal.
 * Returns a ref to attach; adds .revealed when visible (once).
 * Zero deps, respects prefers-reduced-motion via CSS.
 */
export function useReveal<T extends HTMLElement = HTMLDivElement>(threshold = 0.12) {
  const ref = useRef<T | null>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (typeof IntersectionObserver === 'undefined') {
      el.classList.add('revealed')
      return
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add('revealed')
            io.unobserve(e.target)
          }
        }
      },
      { threshold, rootMargin: '0px 0px -8% 0px' }
    )
    io.observe(el)
    return () => io.disconnect()
  }, [threshold])

  return ref
}
