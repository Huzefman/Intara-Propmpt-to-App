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
    <div className="glass" style={{ padding: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <img src="/assets/wish-orb.png" alt="" width={22} height={22} style={{ objectFit: 'contain', filter: 'drop-shadow(0 0 8px rgba(139,92,246,0.6))' }} onError={(e) => (e.currentTarget.style.display = 'none')} />
        <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: '.10em', textTransform: 'uppercase', color: 'var(--intara-muted)' }}>Make a wish</span>
        <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--intara-faint)' }}>{local.length}/500</span>
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
      />
      <div style={{ display: 'flex', gap: 8, marginTop: 12, alignItems: 'center' }}>
        <button onClick={onSubmit} disabled={loading || !local.trim()} className="btn-primary" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {loading ? 'Weaving...' : 'Weave wish →'} {!loading && <span>✦</span>}
        </button>
        <span style={{ fontSize: 11, color: 'var(--intara-faint)' }}>⌘+Enter to send • {loading ? 'Intara is listening...' : 'Debounced 350ms'}</span>
      </div>
    </div>
  )
}
