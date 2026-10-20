import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  deleteAccountKey,
  getAccount,
  saveAccountKey,
  testAccountKey,
  testSavedAccountKey,
  type AccountInfo,
  type AccountKey,
  type AccountProvider,
  type KeyTestResult,
} from '../api/client'

type Tone = 'ok' | 'err' | 'info'
type Msg = { tone: Tone; text: string }

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
  colorScheme: 'dark',
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

const eyebrow: React.CSSProperties = {
  fontSize: 10.5,
  fontWeight: 600,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  color: 'var(--intara-faint)',
}

function toneColors(tone: Tone) {
  if (tone === 'ok') return { border: 'rgba(52,211,153,0.35)', bg: 'rgba(52,211,153,0.06)', color: '#6EE7B7' }
  if (tone === 'err') return { border: 'rgba(248,113,113,0.35)', bg: 'rgba(248,113,113,0.06)', color: '#FCA5A5' }
  return { border: 'rgba(139,92,246,0.35)', bg: 'rgba(139,92,246,0.06)', color: 'var(--intara-nebula-light)' }
}

function Message({ msg }: { msg: Msg | null }) {
  if (!msg) return null
  const c = toneColors(msg.tone)
  return (
    <div
      role={msg.tone === 'err' ? 'alert' : 'status'}
      style={{
        marginTop: 12,
        padding: '10px 12px',
        borderRadius: 12,
        border: `1px solid ${c.border}`,
        background: c.bg,
        color: c.color,
        fontSize: 11.8,
        lineHeight: 1.65,
        letterSpacing: '-0.005em',
        overflowWrap: 'anywhere',
      }}
    >
      {msg.text}
    </div>
  )
}

function Badge({ label, tone = 'default' }: { label: string; tone?: 'default' | 'nebula' | 'green' | 'amber' }) {
  const tones = {
    default: { border: 'rgba(255,255,255,0.08)', color: 'var(--intara-faint)', bg: 'rgba(255,255,255,0.02)' },
    nebula: { border: 'rgba(139,92,246,0.45)', color: 'var(--intara-nebula-light)', bg: 'rgba(139,92,246,0.08)' },
    green: { border: 'rgba(52,211,153,0.35)', color: '#6EE7B7', bg: 'rgba(52,211,153,0.06)' },
    amber: { border: 'rgba(251,191,36,0.35)', color: '#FCD34D', bg: 'rgba(251,191,36,0.06)' },
  }[tone]
  return (
    <span
      style={{
        fontSize: 10.5,
        fontWeight: 500,
        letterSpacing: '0.02em',
        padding: '4px 9px',
        borderRadius: 999,
        border: `1px solid ${tones.border}`,
        color: tones.color,
        background: tones.bg,
        whiteSpace: 'nowrap',
      }}
    >
      {label}
    </span>
  )
}

function when(iso: string | null): string {
  if (!iso) return ''
  const t = Date.parse(iso)
  if (!Number.isFinite(t)) return ''
  return new Date(t).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function testMessage(result: KeyTestResult, fallback: string): Msg {
  if (result.ok) {
    const who = [result.provider, result.model].filter(Boolean).join(' · ')
    return {
      tone: 'ok',
      text: `${who || 'The provider'} answered${result.sample ? `: “${result.sample}”` : '.'}`,
    }
  }
  return { tone: 'err', text: result.error || fallback }
}

export function Account() {
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState<AccountInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadErr, setLoadErr] = useState<string | null>(null)
  const [welcome, setWelcome] = useState(params.get('welcome') === '1')
  const [pageMsg, setPageMsg] = useState<Msg | null>(null)

  const [provider, setProvider] = useState('gemini')
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [busy, setBusy] = useState(false)
  const [testBusy, setTestBusy] = useState(false)
  const [formMsg, setFormMsg] = useState<Msg | null>(null)

  const [rowBusy, setRowBusy] = useState<string | null>(null)
  const [rowMsg, setRowMsg] = useState<Record<string, Msg | undefined>>({})

  const providerTouched = useRef(false)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadErr(null)
    try {
      const next = await getAccount()
      setData(next)
      setProvider((current) => {
        if (providerTouched.current && next.providers.some((p) => p.id === current)) return current
        const firstNew = next.providers.find((p) => !next.keys.some((k) => k.provider === p.id))
        return firstNew?.id ?? next.providers[0]?.id ?? current
      })
    } catch (e: any) {
      setLoadErr(e?.message || 'Could not load your account.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Clear the secret whenever the provider changes — keys are never prefilled.
  useEffect(() => {
    setApiKey('')
    setShowKey(false)
    setFormMsg(null)
    // Intentionally run only when the selected provider changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider])

  // Prefill the saved model/endpoint when replacing a key (or when the
  // account data refreshes after save/delete).
  useEffect(() => {
    const ex = data?.keys.find((k) => k.provider === provider)
    setModel(ex?.model || '')
    setBaseUrl(ex?.base_url || '')
  }, [provider, data])

  const providers: AccountProvider[] = data?.providers ?? []
  const meta = useMemo(
    () => providers.find((p) => p.id === provider) ?? providers[0],
    [providers, provider],
  )
  const existing: AccountKey | undefined = data?.keys.find((k) => k.provider === provider)
  const byok = data?.mode === 'byok'
  const quota = data?.quota
  const limit = quota?.limit ?? null
  const used = quota?.used ?? 0
  const remaining = quota?.remaining
  const pct = limit && limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0

  function dismissWelcome() {
    setWelcome(false)
    const next = new URLSearchParams(params)
    next.delete('welcome')
    setParams(next, { replace: true })
  }

  function chooseProvider(id: string) {
    providerTouched.current = true
    // Clear the secret in the same batch as the provider change so a fast
    // Save cannot send the old key to the newly selected provider.
    setApiKey('')
    setShowKey(false)
    setFormMsg(null)
    setProvider(id)
  }

  async function saveDraft(e: FormEvent) {
    e.preventDefault()
    if (busy || !data?.byok_available || !meta) return
    const key = apiKey.trim()
    if (!key) { setFormMsg({ tone: 'err', text: 'Paste an API key first.' }); return }
    if (meta.needs_base_url && !baseUrl.trim()) { setFormMsg({ tone: 'err', text: 'A base URL is required for a custom endpoint.' }); return }

    setBusy(true)
    setFormMsg(null)
    setPageMsg(null)
    const wasEmpty = (data.keys?.length ?? 0) === 0
    try {
      await saveAccountKey(provider, {
        api_key: key,
        model: model.trim() || null,
        base_url: meta.needs_base_url ? baseUrl.trim() : null,
      })
      setApiKey('')
      setShowKey(false)
      setFormMsg({
        tone: 'ok',
        text: `${meta.label} key saved. Builds now use your key${wasEmpty ? ' and skip the shared 3/day quota' : ''}.`,
      })
      await load()
    } catch (e: any) {
      setFormMsg({ tone: 'err', text: e?.message || 'Could not save the key.' })
    } finally {
      setBusy(false)
    }
  }

  async function testDraft() {
    if (testBusy || !meta) return
    const key = apiKey.trim()
    if (!key) { setFormMsg({ tone: 'err', text: 'Paste an API key to test it.' }); return }
    if (meta.needs_base_url && !baseUrl.trim()) { setFormMsg({ tone: 'err', text: 'Add a base URL before testing.' }); return }

    setTestBusy(true)
    setFormMsg(null)
    try {
      const result = await testAccountKey({
        provider,
        api_key: key,
        model: model.trim() || null,
        base_url: meta.needs_base_url ? baseUrl.trim() : null,
      })
      setFormMsg(testMessage(result, 'The provider rejected that key.'))
    } catch (e: any) {
      setFormMsg({ tone: 'err', text: e?.message || 'Could not test the key.' })
    } finally {
      setTestBusy(false)
    }
  }

  async function testSaved(k: AccountKey) {
    if (rowBusy) return
    setRowBusy(k.provider)
    setRowMsg((prev) => ({ ...prev, [k.provider]: undefined }))
    try {
      const result = await testSavedAccountKey(k.provider)
      setRowMsg((prev) => ({ ...prev, [k.provider]: testMessage(result, 'The provider rejected the saved key.') }))
    } catch (e: any) {
      setRowMsg((prev) => ({ ...prev, [k.provider]: { tone: 'err', text: e?.message || 'Could not test the saved key.' } }))
    } finally {
      setRowBusy(null)
    }
  }

  async function removeKey(k: AccountKey) {
    if (rowBusy) return
    const last = (data?.keys.length ?? 0) <= 1
    const ok = window.confirm(
      `Remove your ${k.label} key?${last ? ' Builds will go back to the shared 3/day pool.' : ' Your other saved keys will still be used.'}`,
    )
    if (!ok) return

    setRowBusy(k.provider)
    setRowMsg((prev) => ({ ...prev, [k.provider]: undefined }))
    setPageMsg(null)
    try {
      await deleteAccountKey(k.provider)
      await load()
      if (provider === k.provider) {
        setApiKey('')
        setShowKey(false)
        setFormMsg(null)
      }
      setPageMsg({
        tone: 'ok',
        text: last
          ? 'Key removed. Builds are back on the shared pool — 3 builds per day.'
          : `${k.label} key removed. Your remaining keys are still in use.`,
      })
    } catch (e: any) {
      setRowMsg((prev) => ({ ...prev, [k.provider]: { tone: 'err', text: e?.message || 'Could not remove the key.' } }))
    } finally {
      setRowBusy(null)
    }
  }

  if (loading && !data) {
    return (
      <div className="glass" style={{ padding: 40, textAlign: 'center', borderRadius: 20, maxWidth: 840 }}>
        <div style={{ width: 28, height: 28, border: '2px solid rgba(255,255,255,0.06)', borderTopColor: 'var(--intara-nebula)', borderRadius: '50%', animation: 'spin 0.9s var(--ease-fluid) infinite', margin: '0 auto' }} />
        <div style={{ marginTop: 12, fontSize: 12.5, color: 'var(--intara-faint)' }}>Opening your account…</div>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="glass" style={{ padding: 22, borderRadius: 20, maxWidth: 840 }}>
        <div style={eyebrow}>Account</div>
        <div style={{ marginTop: 10, fontSize: 13, color: '#FCA5A5' }} role="alert">{loadErr || 'Could not load your account.'}</div>
        <button onClick={() => load()} className="btn-primary" style={{ marginTop: 16, padding: '10px 18px', fontSize: 12.5 }}>Try again</button>
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 840, animation: 'fade-in-fluid 0.5s var(--ease-premium) both' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontFamily: 'Space Grotesk', fontSize: 26, fontWeight: 400, letterSpacing: '-0.03em', color: 'var(--intara-text)' }}>Account</div>
          <div style={{ color: 'var(--intara-faint)', fontSize: 12.5, marginTop: 6, letterSpacing: '-0.01em' }}>
            {data.email ? <>{data.email} · </> : null}Your private workspace, build mode and model keys.
          </div>
        </div>
        <Link to="/" className="btn-ghost" style={{ fontSize: 12, padding: '9px 14px', textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}>Back to wishes</Link>
      </div>

      {welcome && (
        <div
          className="glass"
          style={{ marginTop: 18, padding: '14px 16px', borderRadius: 16, border: '1px solid rgba(52,211,153,0.3)', background: 'rgba(52,211,153,0.05)' }}
          role="status"
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: 12.5, fontWeight: 600, color: '#6EE7B7' }}>Welcome to Intara.</div>
              <div style={{ fontSize: 11.8, lineHeight: 1.7, color: 'var(--intara-muted)', marginTop: 4 }}>
                Add your own LLM key below for unlimited builds. Or skip it and use the shared pool — 3 builds per day, resetting at midnight UTC.
              </div>
            </div>
            <button
              type="button"
              onClick={dismissWelcome}
              aria-label="Dismiss welcome message"
              style={{ background: 'none', border: 'none', color: 'var(--intara-faint)', fontSize: 16, lineHeight: 1, cursor: 'pointer', padding: 2 }}
            >×</button>
          </div>
        </div>
      )}

      {loadErr && (
        <div style={{ marginTop: 14 }}>
          <Message msg={{ tone: 'err', text: loadErr }} />
        </div>
      )}

      {/* Build mode */}
      <div className="glass" style={{ marginTop: 18, padding: 18, borderRadius: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <div style={eyebrow}>Build mode</div>
          {loading && <span style={{ fontSize: 10.5, color: 'var(--intara-dim)' }}>Refreshing…</span>}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 11, flexWrap: 'wrap' }}>
          <Badge label={byok ? 'Your own key' : 'Shared free pool'} tone={byok ? 'green' : 'nebula'} />
          <span style={{ fontSize: 12.5, color: 'var(--intara-muted)', lineHeight: 1.6 }}>
            {byok
              ? 'Builds use your saved key first and skip the shared quota.'
              : `Builds use Intara's shared free LLM pool, limited to ${limit ?? 3} per account per day.`}
          </span>
        </div>

        {byok ? (
          <div style={{ marginTop: 12, fontSize: 11.5, lineHeight: 1.7, color: 'var(--intara-faint)' }}>
            Your key is tried first, in most-recently-updated order. If it fails, the build stops and tells you — it will not quietly spend the shared pool. Remove it below to return to the shared mode.
          </div>
        ) : limit != null && limit <= 0 ? (
          <div style={{ marginTop: 12, fontSize: 11.5, color: 'var(--intara-faint)' }}>Shared builds are currently unlimited on this deployment.</div>
        ) : (
          <div style={{ marginTop: 14 }}>
            <div style={{ height: 6, borderRadius: 999, background: 'rgba(255,255,255,0.05)', overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${pct}%`, borderRadius: 999, background: 'linear-gradient(90deg, #8B5CF6, #A78BFA)', transition: 'width 0.5s var(--ease-premium)' }} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, marginTop: 7, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 11, color: 'var(--intara-faint)' }}>{used} used · {remaining ?? 0} left today</span>
              <span style={{ fontSize: 11, color: 'var(--intara-dim)' }}>Resets at midnight UTC</span>
            </div>
          </div>
        )}

        {!data.byok_available && (
          <Message
            msg={{
              tone: 'err',
              text: `Key storage is not set up on this deployment yet. ${data.error || 'Run migration 013 in Supabase, then reload.'}`,
            }}
          />
        )}
        <Message msg={pageMsg} />
      </div>

      {/* Saved keys */}
      <div className="glass" style={{ marginTop: 14, padding: 18, borderRadius: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <div style={eyebrow}>Saved keys</div>
          <span style={{ fontSize: 10.5, color: 'var(--intara-dim)' }}>{data.keys.length} saved</span>
        </div>

        {data.keys.length === 0 ? (
          <div style={{ marginTop: 12, fontSize: 12.5, lineHeight: 1.75, color: 'var(--intara-faint)' }}>
            No keys yet. You are on the shared pool. Add one below to build with your own provider account and lift the 3/day limit.
          </div>
        ) : (
          <div style={{ display: 'grid', gap: 10, marginTop: 12 }}>
            {data.keys.map((k, i) => (
              <div key={k.provider} style={{ border: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.02)', borderRadius: 14, padding: '12px 13px' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <span style={{ fontSize: 12.8, fontWeight: 600, color: 'var(--intara-text)' }}>{k.label}</span>
                      {i === 0 && <Badge label="Tried first" tone="nebula" />}
                      <span style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 10.8, color: 'var(--intara-faint)' }}>{k.masked}</span>
                    </div>
                    <div style={{ fontSize: 11.2, color: 'var(--intara-faint)', marginTop: 5, lineHeight: 1.6, overflowWrap: 'anywhere' }}>
                      {k.model || 'provider default model'}
                      {k.base_url ? ` · ${k.base_url}` : ''}
                      {k.updated_at ? ` · updated ${when(k.updated_at)}` : ''}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <button
                      type="button"
                      onClick={() => testSaved(k)}
                      disabled={!!rowBusy}
                      className="btn-ghost"
                      style={{ fontSize: 11.5, padding: '7px 12px' }}
                    >{rowBusy === k.provider ? 'Testing…' : 'Test'}</button>
                    <button
                      type="button"
                      onClick={() => removeKey(k)}
                      disabled={!!rowBusy}
                      className="btn-ghost"
                      style={{ fontSize: 11.5, padding: '7px 12px', color: '#FCA5A5' }}
                    >Remove</button>
                  </div>
                </div>
                <Message msg={rowMsg[k.provider] ?? null} />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Add / replace key */}
      <div className="glass" style={{ marginTop: 14, padding: 18, borderRadius: 20 }}>
        <div style={eyebrow}>{existing ? 'Replace key' : 'Add a key'}</div>
        <div style={{ marginTop: 8, fontSize: 11.8, lineHeight: 1.7, color: 'var(--intara-faint)' }}>
          Use any supported provider, or point Intara at any OpenAI-compatible endpoint. The key is encrypted before storage and never shown again after saving.
        </div>

        {!meta ? (
          <div style={{ marginTop: 14 }}>
            <Message msg={{ tone: 'err', text: 'The provider catalog did not load. Refresh the page or check the backend.' }} />
          </div>
        ) : (
          <form onSubmit={saveDraft} style={{ display: 'grid', gap: 13, marginTop: 15 }}>
            <div className="account-fields" style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 12 }}>
              <div>
                <label htmlFor="key-provider" style={labelStyle}>Provider</label>
                <select
                  id="key-provider"
                  value={provider}
                  onChange={(e) => chooseProvider(e.target.value)}
                  style={fieldStyle}
                >
                  {providers.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}{data.keys.some((k) => k.provider === p.id) ? ' · saved' : ''}
                    </option>
                  ))}
                </select>
                <div style={{ marginTop: 6, fontSize: 10.8, color: 'var(--intara-dim)', lineHeight: 1.6 }}>{meta.description}</div>
              </div>
              <div>
                <label htmlFor="key-model" style={labelStyle}>Model <span style={{ textTransform: 'none', letterSpacing: 0, fontWeight: 400 }}>(optional)</span></label>
                <input
                  id="key-model"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder={meta.default_model || 'Model name'}
                  spellCheck={false}
                  autoComplete="off"
                  style={fieldStyle}
                />
                <div style={{ marginTop: 6, fontSize: 10.8, color: 'var(--intara-dim)', lineHeight: 1.6 }}>
                  {meta.needs_base_url ? 'Required for custom endpoints.' : `Blank uses ${meta.default_model || 'the provider default'}.`}
                </div>
              </div>
            </div>

            <div>
              <label htmlFor="key-secret" style={labelStyle}>API key</label>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  id="key-secret"
                  type={showKey ? 'text' : 'password'}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={existing ? `Saved ${existing.masked} — paste a new key to replace` : meta.placeholder}
                  spellCheck={false}
                  autoComplete="off"
                  style={{ ...fieldStyle, flex: 1 }}
                />
                <button
                  type="button"
                  onClick={() => setShowKey((v) => !v)}
                  className="btn-ghost"
                  style={{ fontSize: 11.5, padding: '0 14px', whiteSpace: 'nowrap' }}
                  aria-pressed={showKey}
                >{showKey ? 'Hide' : 'Show'}</button>
              </div>
              {meta.docs_url && (
                <div style={{ marginTop: 7, fontSize: 10.8, color: 'var(--intara-dim)' }}>
                  <a href={meta.docs_url} target="_blank" rel="noreferrer" style={{ color: 'var(--intara-nebula-light)', textDecoration: 'none' }}>
                    Get a {meta.label} key ↗
                  </a>
                </div>
              )}
            </div>

            {meta.needs_base_url && (
              <div>
                <label htmlFor="key-base" style={labelStyle}>Base URL</label>
                <input
                  id="key-base"
                  type="url"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder="https://api.example.com/v1"
                  spellCheck={false}
                  autoComplete="off"
                  style={fieldStyle}
                />
                <div style={{ marginTop: 6, fontSize: 10.8, color: 'var(--intara-dim)', lineHeight: 1.6 }}>
                  Must be a public HTTPS endpoint. Local and private network addresses are rejected.
                </div>
              </div>
            )}

            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginTop: 2 }}>
              <button
                type="submit"
                className="btn-primary"
                disabled={busy || testBusy || !data.byok_available || !apiKey.trim()}
                style={{ padding: '10px 18px', fontSize: 12.5 }}
              >{busy ? 'Saving…' : existing ? 'Replace key' : 'Save key'}</button>
              <button
                type="button"
                onClick={testDraft}
                disabled={busy || testBusy || !data.byok_available || !apiKey.trim()}
                className="btn-ghost"
                style={{ padding: '10px 16px', fontSize: 12.5 }}
              >{testBusy ? 'Testing…' : 'Test before saving'}</button>
              {existing && (
                <button
                  type="button"
                  onClick={() => { setApiKey(''); setShowKey(false); setFormMsg(null) }}
                  className="btn-ghost"
                  style={{ padding: '10px 14px', fontSize: 12.5 }}
                >Clear</button>
              )}
            </div>
            <Message msg={formMsg} />
          </form>
        )}
      </div>

      {/* Privacy / how it works */}
      <div className="glass" style={{ marginTop: 14, padding: 16, borderRadius: 18 }}>
        <div style={eyebrow}>How your key is handled</div>
        <div style={{ fontSize: 11.8, lineHeight: 1.85, color: 'var(--intara-faint)', marginTop: 9, letterSpacing: '-0.005em' }}>
          Keys are encrypted at rest with Fernet, scoped to your account, and readable only by Intara's backend service role. The browser never receives a saved key again — testing a saved key happens server-side. Build calls go from the backend directly to your provider; requests are attributed to your account, and using your own key does not count against the shared 3/day pool.
        </div>
        <div style={{ marginTop: 9, fontSize: 11, color: 'var(--intara-dim)', lineHeight: 1.7 }}>
          Looking after the shared pool? Remove the last saved key to return to the 3/day shared mode. Custom endpoints must be public HTTPS URLs.
        </div>
      </div>

      <div style={{ marginTop: 14, fontSize: 11, color: 'var(--intara-dim)' }}>
        <Link to="/templates" style={{ color: 'var(--intara-faint)', textDecoration: 'none' }}>Browse templates</Link>
        <span style={{ margin: '0 8px', opacity: 0.35 }}>·</span>
        <Link to="/archives" style={{ color: 'var(--intara-faint)', textDecoration: 'none' }}>Ask the archives</Link>
      </div>

      <style>{`@media (max-width: 720px) { .account-fields { grid-template-columns: 1fr !important; } }`}</style>
    </div>
  )
}
