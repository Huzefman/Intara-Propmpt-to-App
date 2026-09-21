import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion'

export function PlanetOrb({ pulsing = false, size = 220, interactive = false }: { pulsing?: boolean; size?: number; interactive?: boolean }) {
  const mx = useMotionValue(0.5)
  const my = useMotionValue(0.5)
  const rx = useSpring(useTransform(my, [0, 1], [7, -7]), { stiffness: 120, damping: 18 })
  const ry = useSpring(useTransform(mx, [0, 1], [-7, 7]), { stiffness: 120, damping: 18 })

  function onMove(e: React.MouseEvent<HTMLDivElement>) {
    if (!interactive) return
    const r = e.currentTarget.getBoundingClientRect()
    mx.set((e.clientX - r.left) / r.width)
    my.set((e.clientY - r.top) / r.height)
  }
  function onLeave() {
    mx.set(0.5)
    my.set(0.5)
  }

  return (
    <motion.div
      onMouseMove={onMove}
      onMouseLeave={onLeave}
      style={{ position: 'relative', width: size, height: size, display: 'grid', placeItems: 'center', rotateX: interactive ? rx : 0, rotateY: interactive ? ry : 0, transformPerspective: 800 }}
    >
      {/* premium fluid glow */}
      <div style={{
        position: 'absolute', inset: -32, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(139,92,246,0.22) 0%, rgba(124,58,237,0.12) 42%, transparent 70%)',
        filter: 'blur(24px)',
        opacity: pulsing ? 0.9 : 0.7,
        transition: 'opacity 0.6s var(--ease-premium)',
      }} />
      {/* outer whisper ring */}
      <div style={{
        position: 'absolute', inset: -14, borderRadius: '50%',
        border: '1px solid rgba(255,255,255,0.04)',
        boxShadow: '0 0 40px rgba(139,92,246,0.08) inset',
        pointerEvents: 'none',
      }} />
      <img
        src="/assets/planet-intara.png"
        alt="Intara planet"
        className={pulsing ? 'planet-orb pulsing' : 'planet-orb'}
        style={{ width: size, height: size }}
        onError={(e) => {
          (e.target as HTMLImageElement).style.display = 'none'
          const fallback = document.getElementById('planet-fallback')
          if (fallback) fallback.style.display = 'grid'
        }}
      />
      <div id="planet-fallback" style={{
        display: 'none', width: size, height: size, borderRadius: '50%',
        background: 'radial-gradient(circle at 32% 28%, #C4B5FD 0%, #8B5CF6 28%, #4C1D95 62%, #07070B 100%)',
        boxShadow: '0 0 50px rgba(139,92,246,0.32)',
        placeItems: 'center',
        fontSize: size * 0.42, filter: 'brightness(1.05)',
      }}>◉</div>
      {/* inner highlight */}
      <div style={{
        position: 'absolute', inset: 0, borderRadius: '50%',
        background: 'radial-gradient(ellipse 60% 40% at 30% 22%, rgba(255,255,255,0.10) 0%, transparent 60%)',
        pointerEvents: 'none',
      }} />
    </motion.div>
  )
}
