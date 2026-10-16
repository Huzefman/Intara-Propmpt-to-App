import { Suspense, lazy } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Landing } from './pages/Landing'
import './theme/intara.css'

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
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/wish/:id" element={<WishVault />} />
            <Route path="/runs/:id" element={<RunPage />} />
            <Route path="/templates" element={<GalleryPage />} />
            <Route path="/constellation" element={<Constellation />} />
            <Route path="/archives" element={<Archives />} />
          </Routes>
        </Suspense>
      </Layout>
    </BrowserRouter>
  )
}
