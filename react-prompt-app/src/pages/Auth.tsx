import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { supabase, isSupabaseDemo } from '../supabase'
import { apiFetch } from '../api/client'
import { useAuth } from '../hooks/useAuth'

type Mode = 'signin' | 'signup'

function humanize(message: string): string {
  const m = message.toLowerCase()
  if (m.includes('invalid login credentials')) return 'Email or password is incorrect.'
  if (m.includes('already registered')) return 'That email already has an account — sign in instead.'
  if (m.includes('email not confirmed')) return 'Confirm your email first — check your inbox, then sign in.'
  if (m.includes('password should be at least')) return 'Use at least 6 characters for the password.'
  if (m.includes('unable to validate email')) return 'That email address doesn’t look valid.'
  if (m.includes('rate limit') || m.includes('too many')) return 'Too many attempts — wait a minute and try again.'
  if (m.includes('fetch') || m.includes('network')) return 'Could not reach the account service — check your connection.'
  return message
}

const fieldStyle: React.CSSProperties = {
  width: '100%',
  padding: '12px 14px',
  borderRadius: 14,
  border: '1px solid rgba(255,255,255,0.08)',
  background: 'rgba(255,255,255,0.03)',
  color: 'var(--intara-text)',
  fontSize: 13,
  fontWeight: 400,
  outline: 'none',
  transition: 'border-color 0.3s var(--ease-premium)',
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 10.5,
  fontWeight: 600,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  color: 'var(--intara-faint)',
  marginBottom: 8,
}

export function Auth() {
  const nav = useNavigate()
  const loc = useLocation() as { state?: { from?: string } }
  const [params, setParams] = useSearchParams()
  const { user, loading } = useAuth()
  const [mode, setMode] = useState<Mode>(params.get('mode') === 'signup' ? 'signup' : 'signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const toAccount = useRef(false)

  const from = useMemo(() => {
    const target = loc.state?.from
    return target && target !== '/auth' ? target : '/'
  }, [loc.state])

  useEffect(() => {
    // A fresh signup goes to /account to add a key. Keep this effect from
    // racing that redirect while Supabase emits its auth-state change.
    if (!loading && user && !toAccount.current) nav(from, { replace: true })
  }, [loading, user, from, nav])

  function switchMode(next: Mode) {
    setMode(next)
    setErr(null)
    setNotice(null)
    const p = new URLSearchParams(params)
    if (next === 'signup') p.set('mode', 'signup'); else p.delete('mode')
    setParams(p, { replace: true })
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (busy) return
    setErr(null)
    setNotice(null)

    const clean = email.trim()
    if (!clean || !clean.includes('@')) { setErr('Enter a valid email address.'); return }
    if (password.length < 6) { setErr('Use at least 6 characters for the password.'); return }
    if (mode === 'signup' && password !== confirm) { setErr('The passwords don’t match.'); return }

    setBusy(true)
    try {
      if (mode === 'signup') {
        // Server-side creation: pre-confirmed, so signup is instant even when
        // the Supabase project still has "Confirm email" enabled.
        const res = await apiFetch('/api/auth/signup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: clean, password }),
        })
        if (!res.ok) {
          const j = await res.json().catch(() => ({} as any))
          throw new Error(j?.detail || `Could not create the account (${res.status}).`)
        }
        // From here on, the auth-state listener must not redirect to `from`:
        // a brand-new account should land on the account page once.
        toAccount.current = true
        const { error } = await supabase.auth.signInWithPassword({ email: clean, password })
        if (error) {
          if ((error.message || '').toLowerCase().includes('email not confirmed')) {
            toAccount.current = false
            setMode('signin')
            setNotice('Account created — but this Supabase project still requires email confirmation. Turn off “Confirm email” in Authentication → Providers → Email, then sign in.')
            return
          }
          throw error
        }
        nav('/account?welcome=1', { replace: true })
      } else {
        toAccount.current = false
        const { error } = await supabase.auth.signInWithPassword({ email: clean, password })
        if (error) throw error
        nav(from, { replace: true })
      }
    } catch (e: any) {
      toAccount.current = false
      setErr(humanize(e?.message || 'Could not sign in.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-grid" style={{ maxWidth: 980, margin: '24px auto 0', display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 420px)', gap: 36, alignItems: 'center', animation: 'fade-in-fluid 0.5s var(--ease-premium) both' }}>
      <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }} style={{ display: 'grid', gap: 14 }}>
        <div style={{ fontSize: 10.5, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--intara-nebula-light)' }}>Intara accounts</div>
        <div style={{ fontFamily: 'Space Grotesk', fontSize: 'clamp(28px, 4vw, 38px)', fontWeight: 400, letterSpacing: '-0.04em', lineHeight: 1.02, color: 'var(--intara-text)' }}>
          Your wishes.<br /><span style={{ color: 'var(--intara-muted)', fontWeight: 300 }}>Only yours.</span>
        </div>
        <p style={{ fontSize: 13.5, lineHeight: 1.75, color: 'var(--intara-faint)', maxWidth: 440, letterSpacing: '-0.01em', margin: 0 }}>
          Every account gets a private workspace in the same Intara database — your plans, builds and chat history are scoped to you and invisible to everyone else. Add your own model key for unlimited builds, or use the shared free pool. The public landing and the ten template apps stay open to all.
        </p>
        <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', marginTop: 4 }}>
          {[
            ['Private by default', 'Owner-scoped queries + row-level security'],
            ['3 builds / day', 'On the shared free LLM pool'],
            ['Your key, your quota', 'Add any provider key after signup'],
          ].map(([title, detail]) => (
            <div key={title} style={{ minWidth: 150 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--intara-muted)' }}>{title}</div>
              <div style={{ fontSize: 11, color: 'var(--intara-dim)', marginTop: 3, lineHeight: 1.55 }}>{detail}</div>
            </div>
          ))}
        </div>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.08, ease: [0.16, 1, 0.3, 1] }} className="glass" style={{ padding: 22, borderRadius: 22 }}>
        <div style={{ display: 'flex', gap: 4, padding: 4, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 14 }}>
          {(['signin', 'signup'] as Mode[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => switchMode(m)}
              style={{
                flex: 1, padding: '9px 10px', borderRadius: 10, border: 'none', cursor: 'pointer',
                fontSize: 12, fontWeight: mode === m ? 600 : 450,
                color: mode === m ? 'var(--intara-text)' : 'var(--intara-faint)',
                background: mode === m ? 'rgba(255,255,255,0.08)' : 'transparent',
                transition: 'all 0.3s var(--ease-premium)',
              }}
            >{m === 'signin' ? 'Sign in' : 'Create account'}</button>
          ))}
        </div>

        <form onSubmit={submit} style={{ display: 'grid', gap: 14, marginTop: 18 }}>
          <div>
            <label htmlFor="auth-email" style={labelStyle}>Email</label>
            <input id="auth-email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" style={fieldStyle} autoFocus />
          </div>
          <div>
            <label htmlFor="auth-password" style={labelStyle}>Password</label>
            <input id="auth-password" type="password" autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 6 characters" style={fieldStyle} />
          </div>
          {mode === 'signup' && (
            <div>
              <label htmlFor="auth-confirm" style={labelStyle}>Confirm password</label>
              <input id="auth-confirm" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="Repeat the password" style={fieldStyle} />
            </div>
          )}

          <button type="submit" className="btn-primary" disabled={busy || isSupabaseDemo} style={{ marginTop: 4, padding: '12px 18px', fontSize: 12.5 }}>
            {busy ? 'One moment…' : mode === 'signup' ? 'Create my account' : 'Sign in'}
          </button>
        </form>

        {mode === 'signup' && (
          <div style={{ marginTop: 12, fontSize: 11, lineHeight: 1.7, color: 'var(--intara-dim)' }}>
            Next: add an LLM key for unlimited builds (optional). Skip it to use the shared pool — 3 builds per day.
          </div>
        )}

        {isSupabaseDemo && (
          <div style={{ marginTop: 14, padding: '10px 12px', borderRadius: 12, border: '1px solid rgba(251,191,36,0.35)', background: 'rgba(251,191,36,0.06)', fontSize: 11.5, lineHeight: 1.6, color: '#FCD34D' }}>
            Accounts are not configured in this build — set <code>VITE_SUPABASE_URL</code> and <code>VITE_SUPABASE_ANON_KEY</code>.
          </div>
        )}
        {err && (
          <div role="alert" style={{ marginTop: 14, padding: '11px 13px', borderRadius: 12, border: '1px solid rgba(248,113,113,0.35)', background: 'rgba(248,113,113,0.06)', fontSize: 12, lineHeight: 1.55, color: '#FCA5A5' }}>{err}</div>
        )}
        {notice && (
          <div role="status" style={{ marginTop: 14, padding: '11px 13px', borderRadius: 12, border: '1px solid rgba(52,211,153,0.35)', background: 'rgba(52,211,153,0.06)', fontSize: 12, lineHeight: 1.55, color: '#6EE7B7' }}>{notice}</div>
        )}

        <div style={{ marginTop: 16, fontSize: 11, lineHeight: 1.7, color: 'var(--intara-dim)' }}>
          {mode === 'signup' ? 'Already have an account?' : 'New to Intara?'}{' '}
          <button type="button" onClick={() => switchMode(mode === 'signup' ? 'signin' : 'signup')} style={{ background: 'none', border: 'none', padding: 0, color: 'var(--intara-nebula-light)', fontSize: 11, cursor: 'pointer', fontWeight: 600 }}>
            {mode === 'signup' ? 'Sign in' : 'Create one'}
          </button>
          <span style={{ margin: '0 8px', opacity: 0.35 }}>·</span>
          <Link to="/" style={{ color: 'var(--intara-faint)', textDecoration: 'none' }}>Back to the landing</Link>
        </div>
      </motion.div>

      <style>{`@media (max-width: 820px) { .auth-grid { grid-template-columns: 1fr !important; } }`}</style>
    </div>
  )
}
