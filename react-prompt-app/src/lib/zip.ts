import JSZip from 'jszip'

export type Artifacts = {
  schema: { tables: any[], prisma: string, sql: string }
  frontend: { files: { path: string; content: string }[] }
  backend: { files: { path: string; content: string }[], requirements: string, openapi: any }
  preview?: Record<string, string>
  spec: { readme: string, openapi: any, cites: string[], prd?: any }
}

export async function buildWishZip(artifacts: Artifacts, appName: string) {
  const zip = new JSZip()
  const slug = appName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'intara-wish'
  const root = zip.folder(slug)!
  // schema
  root.file('schema.json', JSON.stringify({ tables: artifacts.schema.tables }, null, 2))
  root.file('schema.prisma', artifacts.schema.prisma)
  root.file('supabase.sql', artifacts.schema.sql)
  // frontend
  const fe = root.folder('frontend')!
  for (const f of artifacts.frontend.files) fe.file(f.path, f.content)
  // backend
  const be = root.folder('backend')!
  for (const f of artifacts.backend.files) be.file(f.path, f.content)
  be.file('requirements.txt', artifacts.backend.requirements)
  be.file('openapi.json', JSON.stringify(artifacts.backend.openapi ?? artifacts.spec.openapi, null, 2))
  // spec
  root.file('README.md', artifacts.spec.readme)
  root.file('PRD.json', JSON.stringify(artifacts.spec.prd ?? {}, null, 2))
  if (artifacts.spec.cites?.length) root.file('CITES.md', artifacts.spec.cites.map((c, i) => `${i + 1}. ${c}`).join('\n\n'))
  return { blob: await zip.generateAsync({ type: 'blob' }), filename: `${slug}.zip` }
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}
