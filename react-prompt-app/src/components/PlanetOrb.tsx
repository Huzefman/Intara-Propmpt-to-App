export function PlanetOrb({ pulsing = false, size = 220 }: { pulsing?: boolean; size?: number }) {
  return (
    <div style={{ position: 'relative', width: size, height: size, display: 'grid', placeItems: 'center' }}>
      {/* nebula glow behind */}
      <div style={{
        position: 'absolute', inset: -26, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(139,92,246,0.32) 0%, rgba(99,102,241,0.18) 45%, transparent 72%)',
        filter: 'blur(18px)',
      }} />
      <img
        src="/assets/planet-intara.png"
        alt="Intara planet"
        className={pulsing ? 'planet-orb pulsing' : 'planet-orb'}
        style={{ width: size, height: size }}
        onError={(e) => {
          // fallback to CSS gradient orb if asset missing
          (e.target as HTMLImageElement).style.display = 'none'
          const fallback = document.getElementById('planet-fallback')
          if (fallback) fallback.style.display = 'grid'
        }}
      />
      <div id="planet-fallback" style={{
        display: 'none', width: size, height: size, borderRadius: '50%',
        background: 'radial-gradient(circle at 30% 30%, #a78bfa 0%, #7c3aed 32%, #1e1b4b 72%, #0a0a12 100%)',
        boxShadow: '0 0 60px rgba(139,92,246,0.5)',
        placeItems: 'center',
        fontSize: size * 0.42, filter: 'brightness(1.1)',
      }}>◉</div>
      {/* subtle ring */}
      <div style={{
        position: 'absolute', inset: -8, borderRadius: '50%',
        border: '1px solid rgba(255,255,255,0.08)',
        boxShadow: '0 0 30px rgba(139,92,246,0.15) inset',
        pointerEvents: 'none',
      }} />
    </div>
  )
}
