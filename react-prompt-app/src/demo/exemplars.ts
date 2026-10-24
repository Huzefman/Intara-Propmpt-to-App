/**
 * Bundled specs for the static demo (VITE_DEMO=1) and for graceful offline
 * fallback in normal builds: the same 10 curated exemplars that are seeded to
 * the exemplars table, imported straight from packages/spec/exemplars/*.json
 * at build time.
 */
import type { AppSpec } from '../../../packages/spec/app-spec.ts'

export type DemoApp = {
  name: string
  app: string
  tagline: string
  domain: string
  source: string
  entities: number
  pages: number
  spec: AppSpec
}

const modules = import.meta.glob('../../../packages/spec/exemplars/*.json', {
  eager: true,
}) as Record<string, { default: AppSpec }>

export const DEMO_APPS: DemoApp[] = Object.entries(modules)
  .map(([path, mod]) => {
    const spec = (mod.default ?? mod) as AppSpec
    const name = path.split('/').pop()!.replace(/\.json$/, '')
    return {
      name,
      app: spec.app?.name ?? name,
      tagline: spec.app?.tagline ?? '',
      domain: spec.app?.domain ?? 'app',
      source: 'gold spec',
      entities: spec.model?.entities?.length ?? 0,
      pages: spec.ui?.pages?.length ?? 0,
      spec,
    }
  })
  .sort((a, b) => a.name.localeCompare(b.name))

export function findDemoApp(name: string): DemoApp | undefined {
  return DEMO_APPS.find((a) => a.name === name)
}
