// Intara — Premium Fluid Minimal — Tokens
export const tokens = {
  colors: {
    bg: '#07070B',
    bgElevated: '#0F0F14',
    bgGlass: 'rgba(255,255,255,0.035)',
    bgGlassHover: 'rgba(255,255,255,0.055)',
    borderGlass: 'rgba(255,255,255,0.06)',
    borderGlassHover: 'rgba(255,255,255,0.10)',
    surface: 'rgba(255,255,255,0.02)',
    nebula: '#8B5CF6',
    nebulaLight: '#A78BFA',
    nebula2: '#7C3AED',
    nebulaGlow: 'rgba(139,92,246,0.28)',
    nebulaGlowSoft: 'rgba(139,92,246,0.12)',
    text: '#F8FAFC',
    textMuted: '#CBD5E1',
    textFaint: '#94A3B8',
    textDim: '#64748B',
    accent: '#8B5CF6',
  },
  radius: {
    sm: '10px',
    md: '16px',
    lg: '20px',
    xl: '24px',
    pill: '999px',
  },
  font: {
    display: '"Space Grotesk", system-ui, sans-serif',
    body: 'Inter, system-ui, sans-serif',
    mono: '"JetBrains Mono", ui-monospace, monospace',
  },
  ease: {
    premium: 'cubic-bezier(0.16, 1, 0.3, 1)',
    fluid: 'cubic-bezier(0.32, 0.72, 0, 1)',
    gentle: 'cubic-bezier(0.25, 0.1, 0.25, 1)',
  },
} as const
