import { Component, type ReactNode } from 'react'

type Props = { children: ReactNode; label: string; onRetry?: () => void }
type State = { error: Error | null }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error) {
    console.error(`[Intara:${this.props.label}]`, error)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="glass" style={{ padding: 24, borderRadius: 16, textAlign: 'center' }} role="alert">
          <div style={{ fontFamily: 'Space Grotesk', fontSize: 15, fontWeight: 500, color: 'var(--intara-text)' }}>
            This {this.props.label} hit a snag
          </div>
          <div style={{ fontSize: 12, color: 'var(--intara-faint)', marginTop: 8, fontFamily: 'JetBrains Mono, monospace', wordBreak: 'break-word' }}>
            {this.state.error.message || String(this.state.error)}
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 14 }}>
            <button
              className="btn-primary btn-sm"
              onClick={() => { this.setState({ error: null }); this.props.onRetry?.() }}
            >
              Retry
            </button>
            <button className="btn-ghost btn-sm" onClick={() => window.location.reload()}>Reload page</button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
