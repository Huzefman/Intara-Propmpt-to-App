import { useEffect, useState } from 'react'

export function WishInput({
  value,
  onChange,
  onSubmit,
  loading,
  placeholder = 'I wish for a...',
  autoFocus,
}: {
  value: string
  onChange: (v: string) => void
  onSubmit: () => void
  loading?: boolean
  placeholder?: string
  autoFocus?: boolean
}) {
  const [local, setLocal] = useState(value)
  useEffect(() => setLocal(value), [value])
  // debounced onChange upstream (350ms) is handled by parent; this is immediate local
  return (
    <div className="glass" style={{ padding: 22, borderRadius: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
        <img src="/assets/wish-orb.png" alt="" width={22} height={22} style={{ objectFit: 'contain', filter: 'drop-shadow(0 0 10px rgba(139,92,246,0.36))', opacity: 0.9 }} onError={(e) => (e.currentTarget.style.display = 'none')} />
        <span style={{ fontSize: 12.5, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--intara-nebula-light)' }}>Describe your app</span>
        <span style={{ marginLeft: 'auto', fontSize: 12.5, fontWeight: 450, color: 'var(--intara-dim)', fontVariantNumeric: 'tabular-nums' }}>{local.length}<span style={{ opacity: 0.5 }}> / 500</span></span>
      </div>
      <textarea
        value={local}
        onChange={(e) => { setLocal(e.target.value); onChange(e.target.value) }}
        onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) onSubmit() }}
        rows={3}
        maxLength={500}
        placeholder={placeholder}
        autoFocus={autoFocus}
        className="wish-input"
        aria-label="Wish prompt"
      />
      <div style={{ display: 'flex', gap: 12, marginTop: 16, alignItems: 'center', flexWrap: 'wrap' }}>
        <button onClick={onSubmit} disabled={loading || !local.trim()} className="btn-primary" style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '12px 24px', fontSize: 15 }}>
          <span style={{ fontWeight: 600 }}>{loading ? 'Creating app…' : 'Generate App'}</span>
          <span style={{ opacity: 0.9, fontSize: 14, transition: 'transform 0.3s var(--ease-premium)', display: 'inline-block', transform: loading ? 'rotate(180deg)' : 'none' }}>→</span>
          {!loading && <span style={{ marginLeft: -2, fontSize: 12, opacity: 0.8 }}>✦</span>}
        </button>
        <span style={{ fontSize: 13, fontWeight: 400, color: 'var(--intara-faint)', letterSpacing: '-0.01em' }}>
          <span style={{ color: 'var(--intara-text)' }}>⌘+Enter</span> to generate <span style={{ opacity: 0.3, margin: '0 6px' }}>·</span> {loading ? <span style={{ color: 'var(--intara-nebula-light)' }}>Intara is designing your app…</span> : 'Instant AI Generation'}
        </span>
      </div>
    </div>
  )
}
