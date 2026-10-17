/**
 * Capture screenshots of the static demo with the system Chrome — no
 * browser download needed (playwright-core).
 *
 *   npm run build            # with VITE_DEMO=1 for the demo bundle
 *   npm run preview          # serves dist on :4173
 *   node scripts/capture.mjs # writes PNGs to ../docs/assets/
 *
 * Also doubles as the offline smoke test: fails (exit 1) on page errors or
 * if the gallery/app don't render.
 */
import { chromium } from 'playwright-core'
import { mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const BASE = process.env.CAPTURE_URL || 'http://localhost:4173'
const OUT = path.resolve(fileURLToPath(new URL('.', import.meta.url)), '../../docs/assets')
mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch({ channel: 'chrome' })
const page = await browser.newPage({ viewport: { width: 1360, height: 900 }, deviceScaleFactor: 2 })

const problems = []
page.on('pageerror', (e) => problems.push(`pageerror: ${e}`))
page.on('console', (m) => { if (m.type() === 'error') problems.push(`console: ${m.text()}`) })
page.on('response', (r) => {
  if (r.status() >= 400 && !r.url().includes('favicon')) problems.push(`http ${r.status()}: ${r.url()}`)
})

async function shot(name, locator) {
  const target = locator ?? page
  await target.screenshot({ path: path.join(OUT, name) })
  console.log(`saved docs/assets/${name}`)
}

console.log(`→ ${BASE}/`)
await page.goto(`${BASE}/`, { waitUntil: 'networkidle' })
await page.waitForTimeout(600)
await shot('demo-landing.png')

await page.getByRole('button', { name: /Open the 10 live apps/ }).click()
await page.waitForSelector('text=✦ Templates', { timeout: 15000 })
await page.waitForTimeout(400)
await shot('demo-gallery.png')

const cards = page.locator('button.glass').filter({ hasText: 'entities' })
const n = await cards.count()
if (n < 10) throw new Error(`expected 10 gold apps in the gallery, found ${n}`)
console.log(`gallery: ${n} apps`)

/** Open an app, optionally click nav pages, screenshot the runtime shell. */
async function appShot(label, file, pages = []) {
  await page.goto(`${BASE}/templates`, { waitUntil: 'networkidle' })
  await page.waitForSelector('text=✦ Templates', { timeout: 15000 })
  await cards.filter({ hasText: label }).first().click()
  const shell = page.locator('.app-shell').first()
  await shell.waitFor({ timeout: 20000 })
  await shell.locator('.app-nav button').first().waitFor({ timeout: 20000 })
  await page.waitForTimeout(500)
  for (const p of pages) {
    await shell.getByRole('button', { name: p, exact: true }).click()
    await page.waitForTimeout(450)
  }
  await shell.scrollIntoViewIfNeeded()
  await shot(file, shell)
}

await appShot('Stockroom', 'demo-app-stockroom.png', ['Items'])
await appShot('TaskFlow', 'demo-app-taskflow-board.png', ['Board'])
await appShot('PawCare', 'demo-app-pawcare-visits.png', ['Visits'])

const real = problems.filter((p) => !p.includes('favicon'))
await browser.close()
if (real.length) {
  console.error('page problems:\n' + real.join('\n'))
  process.exit(1)
}
console.log('offline smoke: OK (no page errors)')
