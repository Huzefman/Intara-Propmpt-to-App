import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Landing } from './pages/Landing'
import { WishVault } from './pages/WishVault'
import { Constellation } from './pages/Constellation'
import { Archives } from './pages/Archives'
import './theme/intara.css'

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/wish/:id" element={<WishVault />} />
          <Route path="/constellation" element={<Constellation />} />
          <Route path="/archives" element={<Archives />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}
