import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
export default defineConfig({
  plugins: [react()],
  resolve: { alias: {
    '@': path.resolve(__dirname, './src'),
    // Single React copy for the Studio bundle incl. packages/runtime blocks.
    // (packages/runtime keeps its own react for node-side render smoke.)
    'react': path.resolve(__dirname, './node_modules/react'),
    'react-dom': path.resolve(__dirname, './node_modules/react-dom'),
  } },
  server: { port: 5173, proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true, rewrite: (path) => path.replace(/^\/api/, '') } } }
})
