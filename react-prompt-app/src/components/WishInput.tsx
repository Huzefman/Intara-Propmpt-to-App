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
    <div className="glass" style={{ padding: 18, borderRadius: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <img src="/assets/wish-orb.png" alt="" width={20} height={20} style={{ objectFit: 'contain', filter: 'drop-shadow(0 0 10px rgba(139,92,246,0.36))', opacity: 0.9 }} onError={(e) => (e.currentTarget.style.display = 'none')} />
        <span style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--intara-faint)' }}>Make a wish</span>
        <span style={{ marginLeft: 'auto', fontSize: 11, fontWeight: 400, color: 'var(--intara-dim)', fontVariantNumeric: 'tabular-nums' }}>{local.length}<span style={{ opacity: 0.5 }}> / 500</span></span>
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
      <div style={{ display: 'flex', gap: 10, marginTop: 14, alignItems: 'center', flexWrap: 'wrap' }}>
        <button onClick={onSubmit} disabled={loading || !local.trim()} className="btn-primary" style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '11px 20px' }}>
          <span style={{ fontWeight: 550 }}>{loading ? 'Weaving…' : 'Weave wish'}</span>
          <span style={{ opacity: 0.9, fontSize: 13, transition: 'transform 0.3s var(--ease-premium)', display: 'inline-block', transform: loading ? 'rotate(180deg)' : 'none' }}>→</span>
          {!loading && <span style={{ marginLeft: -2, fontSize: 11, opacity: 0.8 }}>✦</span>}
        </button>
        <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--intara-dim)', letterSpacing: '-0.01em' }}>
          <span style={{ color: 'var(--intara-faint)' }}>⌘+Enter</span> to send <span style={{ opacity: 0.3, margin: '0 6px' }}>·</span> {loading ? <span style={{ color: 'var(--intara-nebula-light)' }}>Intara is listening…</span> : 'Fluid • debounced'}
        </span>
      </div>
    </div>
  )
}
