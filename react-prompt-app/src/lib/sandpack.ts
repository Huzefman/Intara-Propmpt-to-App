import type { Artifacts } from './zip'

export function toSandpackFiles(artifacts: Artifacts) {
  const files: Record<string, { code: string; hidden?: boolean }> = {}
  const list = (artifacts as any)?.frontend?.files
  if (Array.isArray(list)) {
    for (const f of list) {
      if (!f || typeof f.path !== 'string') continue
      // Sandpack expects leading slash
      const path = `/${f.path}`
      const hidden = f.path === 'package.json' || f.path.startsWith('src/mock/') || f.path === 'vite.config.ts' || f.path === 'tsconfig.json'
      files[path] = { code: typeof f.content === 'string' ? f.content : '', hidden }
    }
  }
  // ensure entry
  if (!files['/src/main.tsx']) {
    files['/src/main.tsx'] = { code: `import React from 'react'\nimport ReactDOM from 'react-dom/client'\nimport App from './App'\nReactDOM.createRoot(document.getElementById('root')!).render(<App />)` }
  }
  return files
}
