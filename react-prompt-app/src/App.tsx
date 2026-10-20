import { Suspense, lazy } from 'react'
import { BrowserRouter, Navigate, Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { RequireAuth } from './components/RequireAuth'
import { Landing } from './pages/Landing'
import { DEMO } from './demo'
import './theme/intara.css'

const Auth = lazy(() => import('./pages/Auth').then(m => ({ default: m.Auth })))
const Account = lazy(() => import('./pages/Account').then(m => ({ default: m.Account })))
const WishVault = lazy(() => import('./pages/WishVault').then(m => ({ default: m.WishVault })))
const Constellation = lazy(() => import('./pages/Constellation').then(m => ({ default: m.Constellation })))
const Archives = lazy(() => import('./pages/Archives').then(m => ({ default: m.Archives })))
const RunPage = lazy(() => import('./pages/RunPage').then(m => ({ default: m.RunPage })))
const GalleryPage = lazy(() => import('./pages/GalleryPage').then(m => ({ default: m.GalleryPage })))

function RouteFallback() {
  return <div className="glass" style={{ padding: 40, textAlign: 'center', borderRadius: 20 }}>
    <div style={{ width: 28, height: 28, border: '2px solid rgba(255,255,255,0.06)', borderTopColor: 'var(--intara-nebula)', borderRadius: '50%', animation: 'spin 0.9s var(--ease-fluid) infinite', margin: '0 auto' }} />
    <div style={{ marginTop: 12, fontSize: 12.5, color: 'var(--intara-faint)' }}>Drifting through the nebula…</div>
    <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
  </div>
}

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Suspense fallback={<RouteFallback />}>
          {DEMO ? (
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/templates" element={<GalleryPage />} />
              <Route path="*" element={<Navigate to="/templates" replace />} />
            </Routes>
          ) : (
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/auth" element={<Auth />} />
              <Route path="/account" element={<RequireAuth><Account /></RequireAuth>} />
              <Route path="/wish/:id" element={<RequireAuth><WishVault /></RequireAuth>} />
              <Route path="/runs/:id" element={<RequireAuth><RunPage /></RequireAuth>} />
              <Route path="/templates" element={<GalleryPage />} />
              <Route path="/constellation" element={<RequireAuth><Constellation /></RequireAuth>} />
              <Route path="/archives" element={<RequireAuth><Archives /></RequireAuth>} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          )}
        </Suspense>
      </Layout>
    </BrowserRouter>
  )
}
