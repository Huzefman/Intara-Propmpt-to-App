/** Template gallery route. */
import { GalleryView } from '../components/GalleryView'

export function GalleryPage() {
  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '20px 16px 60px', display: 'grid', gap: 12 }}>
      <GalleryView />
    </div>
  )
}
