/**
 * QA interaction sweep (QA pass 2) — every actionable control in all 10 gold
 * apps, driven by the exemplar specs themselves.
 *
 *   node scripts/qa-interact.mjs                  # → http://localhost:5173
 *   QA_URL=http://localhost:4173 node scripts/qa-interact.mjs
 *
 * Per app (fresh browser context ⇒ clean IndexedDB): open via /templates,
 * check the role switcher, then for the primary role walk every nav page and
 * exercise — "New"/"Add" dialogs (create, related-list prefill, singleton
 * settings save + persistence), filter bar (search + field filters), CSV
 * export (real download) and import, lifecycle transitions, kanban drags
 * (move or a clear refusal notice), row/kanban/calendar opens (navigation to
 * the detail page), then walk the nav of every other role incl. their
 * transitions. Host controls (Print stub, Set PIN / Lock / Unlock) are
 * exercised too. Fails on any console/page error or failed assertion and
 * saves screenshots under docs/assets/qa/.
 */
import { chromium } from 'playwright-core'
import { mkdirSync, readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const BASE = process.env.QA_URL || 'http://localhost:5173'
const HERE = path.dirname(fileURLToPath(import.meta.url))
const EX_DIR = path.resolve(HERE, '../../packages/spec/exemplars')
const SHOTS = path.resolve(HERE, '../../docs/assets/qa')
mkdirSync(SHOTS, { recursive: true })

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

const specs = readdirSync(EX_DIR).filter((f) => f.endsWith('.json')).sort()
  .map((f) => JSON.parse(readFileSync(path.join(EX_DIR, f), 'utf8')))
  .filter((s) => !process.env.QA_APPS || process.env.QA_APPS.split(',').some((a) => s.app.name.toLowerCase().includes(a.trim().toLowerCase())))

// ---- spec helpers -----------------------------------------------------------

function rolesFor(spec) {
  const covered = new Set()
  for (const p of spec.ui.pages) {
    const pr = p.roles ?? []
    if (pr.length === 0) for (const r of spec.access.roles) covered.add(r.id)
    else for (const r of pr) covered.add(r)
  }
  return spec.access.roles.map((r) => r.id).filter((id) => covered.has(id))
}

function navFor(spec, role) {
  const pages = new Map(spec.ui.pages.map((p) => [p.id, p]))
  const out = []
  for (const n of spec.ui.nav ?? []) {
    const p = pages.get(n.page)
    if (!p) continue
    const itemRoles = n.roles ?? []
    const pageRoles = p.roles ?? []
    if ((!itemRoles.length || itemRoles.includes(role)) && (!pageRoles.length || pageRoles.includes(role))) {
      out.push({ pageId: p.id, label: n.label })
    }
  }
  return out
}

function detailPageFor(spec, entity) {
  return spec.ui.pages.find((p) => (p.blocks ?? []).some((b) =>
    b.type === 'record.detail' && (b.props ?? {}).entity === entity))?.id ?? null
}

/** Where does an open-like click on this block navigate? (mirrors host logic) */
function linkTarget(spec, block) {
  const props = block.props ?? {}
  if (block.type === 'data.table' || block.type === 'record.related_list') return props.row_link ?? null
  if (block.type === 'data.kanban' || block.type === 'calendar.month') return props.row_link ?? detailPageFor(spec, props.entity)
  return null
}

async function synthDrag(page, card, target) {
  const c = await card.elementHandle()
  const t = await target.elementHandle()
  if (!c || !t) return
  await page.evaluate(([cardEl, colEl]) => {
    const dt = new DataTransfer()
    cardEl.dispatchEvent(new DragEvent('dragstart', { bubbles: true, cancelable: true, dataTransfer: dt }))
    colEl.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: dt }))
    colEl.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }))
    cardEl.dispatchEvent(new DragEvent('dragend', { bubbles: true, cancelable: true, dataTransfer: dt }))
  }, [c, t])
}

// ---- per-app sweep ----------------------------------------------------------

async function qaApp(browser, spec, { withPin }) {
  const app = spec.app.name
  const appSlug = slug(app)
  const pagesById = new Map(spec.ui.pages.map((p) => [p.id, p]))
  const issues = []
  let checks = 0
  let shots = 0

  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true })
  const page = await context.newPage()
  page.setDefaultTimeout(8000)
  const errs = []
  page.on('pageerror', (e) => errs.push(`pageerror: ${e.message}`))
  page.on('console', (m) => {
    if (m.type() === 'error' && !/favicon/.test(m.text())) errs.push(`console: ${m.text()}`)
  })
  await page.addInitScript(() => {
    window.__printCount = 0
    window.print = () => { window.__printCount += 1 }
  })

  const fail = (msg) => {
    issues.push(msg)
    checks += 1
    console.log(`   ✗ ${msg}`)
    shots += 1
    if (shots <= 3) void page.screenshot({ path: path.join(SHOTS, `${appSlug}-f${shots}.png`) }).catch(() => {})
  }
  const expect = (cond, msg) => { if (!cond) fail(msg); else checks += 1 }
  const waitFor = async (fn, timeout = 5000, step = 120) => {
    const t0 = Date.now()
    for (;;) {
      if (await fn().catch(() => false)) return true
      if (Date.now() - t0 > timeout) return false
      await sleep(step)
    }
  }

  try {
    await page.goto(`${BASE}/templates`, { waitUntil: 'networkidle' })
    await page.waitForSelector('text=✦ Templates', { timeout: 20000 })
    await page.locator('button.glass').filter({ hasText: app }).first().click()
    const shell = page.locator('.app-shell').first()
    await shell.waitFor({ timeout: 20000 })
    await shell.locator('.app-nav button').first().waitFor({ timeout: 20000 })
    const roots = shell.locator('.app-main > .blk:not([role="status"])')
    const root = (i) => roots.nth(i)
    await roots.first().waitFor({ timeout: 20000 })
    await sleep(350)

    const settle = (ms = 250) => sleep(ms)
    const noticeText = async () =>
      (await page.locator('[role="status"]').count()) ? (await page.locator('[role="status"]').innerText()) : ''

    // ---- controls the whole sweep relies on
    let role = rolesFor(spec)[0]
    let currentPage = spec.ui.pages[0]?.id ?? ''
    const navBar = shell.locator('.app-nav')
    const navClick = async (label, pid) => {
      await navBar.getByRole('button', { name: label, exact: true }).click()
      if (pid) await waitFor(async () => (await activeNavPage()) === pid, 3000)
    }
    const activeNavPage = async () => {
      const label = await shell.locator('.app-nav button.active').innerText().catch(() => '')
      return navFor(spec, role).find((e) => e.label === label)?.pageId ?? null
    }

    // ---- role switcher
    const roleSel = shell.locator('select[aria-label="role"]')
    const roleOpts = await roleSel.locator('option').evaluateAll((os) => os.map((o) => o.value))
    const rolesWant = rolesFor(spec)
    expect(JSON.stringify(roleOpts) === JSON.stringify(rolesWant),
      `role options ${JSON.stringify(roleOpts)} != ${JSON.stringify(rolesWant)}`)

    // ---- navigation helpers
    const clickLink = async (pid, targetId) => {
      const blocks = pagesById.get(pid).blocks ?? []
      for (let i = 0; i < blocks.length; i++) {
        const b = blocks[i]
        if (linkTarget(spec, b) !== targetId) continue
        const r = root(i)
        let el = null
        if (b.type === 'data.table') el = r.locator('.blk-table tbody tr').first()
        else if (b.type === 'record.related_list') el = r.locator('.blk-related li').first()
        else if (b.type === 'data.kanban') el = r.locator('.blk-card').first()
        else if (b.type === 'calendar.month') el = r.locator('.blk-day button').first()
        if (!el || (await el.count()) === 0) continue
        await el.click()
        return true
      }
      return false
    }
    const ensure = async (pid) => {
      if (currentPage === pid) return true
      const seen = new Set()
      const go = async (id) => {
        if (seen.has(id)) return false
        seen.add(id)
        if (currentPage === id) return true
        const entry = navFor(spec, role).find((e) => e.pageId === id)
        if (entry) {
          await navClick(entry.label, id)
          currentPage = id
          return true
        }
        // detail pages can be reachable from several parents; try each until
        // one actually has a clickable row (an empty related list can't open).
        const parents = spec.ui.pages.filter((p) => (p.blocks ?? []).some((b) => linkTarget(spec, b) === id))
        for (const p of parents) {
          if (!(await go(p.id))) continue
          if (await clickLink(p.id, id)) { await settle(350); currentPage = id; return true }
        }
        return false
      }
      return go(pid)
    }
    const expectArrived = async (targetId, clickedText) => {
      const t = pagesById.get(targetId)
      const di = (t.blocks ?? []).findIndex((b) => b.type === 'record.detail')
      if (di >= 0) {
        try {
          await root(di).locator('.blk-detail').first().waitFor({ timeout: 5000 })
        } catch {
          fail(`open → ${targetId}: no record detail rendered`)
          return
        }
        if (clickedText) {
          const txt = await root(di).innerText().catch(() => '')
          if (!txt.includes(clickedText.slice(0, 12))) {
            console.log(`   ~ detail on ${targetId} does not contain "${clickedText.slice(0, 24)}" (review)`)
          }
        }
      } else {
        await settle(350)
      }
    }

    // ---- generic dialog filler
    const fillDialog = async (modal) => {
      const selects = modal.locator('select')
      for (let s = 0; s < await selects.count(); s++) {
        const el = selects.nth(s)
        const multi = await el.evaluate((x) => x.multiple)
        const cur = await el.evaluate((x) => x.value)
        const vals = await el.evaluate((x) => Array.from(x.options).map((o) => o.value).filter(Boolean))
        if (!vals.length) continue
        if (multi) await el.selectOption([vals[0]]).catch(() => {})
        else if (!cur) await el.selectOption(vals[0]).catch(() => {})
      }
      const inputs = modal.locator('input:not([type=checkbox]), textarea')
      for (let k = 0; k < await inputs.count(); k++) {
        const el = inputs.nth(k)
        const cur = await el.inputValue().catch(() => '')
        if (cur) continue
        const type = (await el.getAttribute('type')) || 'text'
        const val = type === 'date' ? '2026-11-05' : type === 'datetime-local' ? '2026-11-05T10:00'
          : type === 'time' ? '10:00' : type === 'number' ? '3' : type === 'color' ? '#8b5cf6'
            : type === 'email' ? 'qa@example.com' : type === 'tel' ? '5550100'
              : type === 'url' ? 'https://example.com/qa.txt' : 'QA note'
        await el.fill(val).catch((e) => fail(`dialog fill "${type}" failed: ${e.message}`))
      }
    }

    // ---- probes -----------------------------------------------------------------

    const probeFilter = async (i, b, pid) => {
      const blockList = pagesById.get(pid).blocks ?? []
      const tblIdx = blockList.findIndex((x) => x.type === 'data.table' && (x.props ?? {}).entity === b.props.entity)
      const count = async () => (tblIdx >= 0 ? root(tblIdx).locator('.blk-table tbody tr').count() : 0)
      const search = root(i).locator('input[aria-label="search"]')
      const before = await count()
      if ((await search.count()) && before > 0) {
        const cols = (blockList[tblIdx]?.props ?? {}).columns ?? []
        const cands = (b.props.search ?? []).filter((f) => cols.includes(f))
        // Read candidate cells from the unfiltered table first: a prior
        // needle may filter every row away, and reading a cell then hangs.
        const cells = []
        for (const c of cands.slice(0, 2)) {
          const ci = cols.indexOf(c)
          const tds = root(tblIdx).locator('.blk-table tbody tr').first().locator('td')
          if (ci < 0 || (await tds.count()) <= ci) continue
          const cell = (await tds.nth(ci).innerText().catch(() => '')).trim()
          if (cell) cells.push(cell)
        }
        let ok = false
        if (cells.length) {
          for (const cell of cells) {
            await search.fill(cell.slice(0, Math.max(3, Math.min(8, cell.length))))
            await settle(200)
            const d = await count()
            ok = before > 1 ? d >= 1 && d < before : d >= 1
            if (ok) break
          }
        } else {
          await search.fill('zzz-no-such-value'); await settle(200)
          ok = (await count()) === 0
        }
        expect(ok, `filter search on ${pid} did not filter (rows ${before})`)
        await search.fill(''); await settle(200)
        expect((await count()) === before, `filter search clear on ${pid} did not restore rows`)
      }
      for (const f of b.props.fields ?? []) {
        const inp = root(i).locator(`input[aria-label="${f}"]`)
        if ((await inp.count()) === 0) continue
        const cols = (blockList[tblIdx]?.props ?? {}).columns ?? []
        let needle = 'zzz-no-such'
        if (tblIdx >= 0 && cols.includes(f) && (await count()) > 0) {
          const cell = (await root(tblIdx).locator('.blk-table tbody tr').first().locator('td').nth(cols.indexOf(f)).innerText()).trim()
          if (cell) needle = cell.slice(0, 8)
        }
        await inp.fill(needle); await settle(200)
        const d = await count()
        expect(needle === 'zzz-no-such' ? d === 0 : d >= 1, `field filter "${f}" on ${pid} gave ${d} rows (needle "${needle}")`)
        await inp.fill(''); await settle(150)
      }
    }

    const probeCreate = async (i, b, pid, isRelated) => {
      const btn = root(i).getByRole('button', { name: isRelated ? 'Add' : 'New', exact: true })
      if ((await btn.count()) === 0) {
        const cls = await root(i).evaluate((el) => el.className).catch(() => '?')
        fail(`${b.type} on ${pid} declares create but rendered no button (root: ${cls})`)
        return
      }
      const rowCount = async () => (isRelated
        ? root(i).locator('.blk-related li').count()
        : root(i).locator('.blk-table tbody tr').count())
      const before = await rowCount()
      await btn.click()
      const modal = page.locator('.blk-modal')
      try { await modal.waitFor({ timeout: 4000 }) } catch { fail(`create dialog did not open on ${pid}`); return }
      if (isRelated && b.props.via) {
        const via = b.props.via
        let prefillVal = null
        const prefillOk = await waitFor(async () => {
          prefillVal = await modal.evaluate((m, fid) => {
            const wanted = fid.replace(/_/g, ' ').toLowerCase()
            for (const l of m.querySelectorAll('label')) {
              const t = (l.textContent || '').trim().toLowerCase()
              if (t.startsWith(wanted)) {
                const s = l.querySelector('select')
                if (s) return s.value || ''
                const inp = l.querySelector('input')
                if (inp) return inp.value || ''
              }
            }
            return null
          }, via).catch(() => null)
          return prefillVal !== null && prefillVal !== ''
        }, 2500)
        expect(prefillOk, `related Add on ${pid} did not prefill "${via}" (got ${JSON.stringify(prefillVal)})`)
      }
      await fillDialog(modal)
      await modal.getByRole('button', { name: /^(Create|Save)$/ }).click()
      try {
        await modal.waitFor({ state: 'detached', timeout: 4000 })
      } catch {
        const invalid = await modal.evaluate((m) => {
          const out = []
          for (const el of m.querySelectorAll('input, select, textarea')) {
            if (!el.checkValidity()) out.push(((el.closest('label')?.textContent ?? el.tagName)).trim().slice(0, 40))
          }
          return out
        })
        fail(`create dialog on ${pid} did not submit (invalid: ${JSON.stringify(invalid)})`)
        await modal.getByRole('button', { name: 'Cancel' }).click().catch(() => {})
        return
      }
      // the save is async (adapter + refresh + automations): wait for the row
      const added = await waitFor(async () => (await rowCount()) >= before + 1)
      expect(added, `create on ${pid} did not add a row (${before} → ${await rowCount()})`)
      expect(/Created|Saved/.test(await noticeText()), `create on ${pid} gave no notice (got "${(await noticeText()).slice(-70)}")`)
    }

    const probeExport = async (i, b, pid) => {
      const btn = root(i).getByRole('button', { name: 'Export CSV', exact: true })
      if ((await btn.count()) === 0) return
      try {
        const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 6000 }), btn.click()])
        const name = dl.suggestedFilename()
        expect(name === `${b.props.entity}.csv`, `export on ${pid}: filename "${name}"`)
      } catch {
        fail(`export on ${pid} produced no download`)
      }
    }

    const probeImport = async (i, b, pid) => {
      const inp = root(i).locator('input[type=file]')
      if ((await inp.count()) === 0) return
      const ent = spec.model.entities.find((e) => e.id === b.props.entity)
      const f = ent?.fields.find((x) => x.type === 'text' && !x.computed)
        ?? ent?.fields.find((x) => !['ref', 'multi_ref', 'enum', 'multi_enum', 'bool', 'file', 'image', 'date', 'datetime'].includes(x.type) && !x.computed)
        ?? ent?.fields.find((x) => !x.computed)
      if (!f) return
      const val = ['int', 'decimal', 'money', 'rating'].includes(f.type) ? '9'
        : f.type === 'date' ? '2026-11-05' : f.type === 'datetime' ? '2026-11-05T09:00' : `QA import ${Date.now()}`
      const rows = () => root(i).locator('.blk-table tbody tr').count()
      const before = await rows()
      await inp.setInputFiles({ name: 'qa-import.csv', mimeType: 'text/csv', buffer: Buffer.from(`${f.id}\n${val}\n`) })
      const added = await waitFor(async () => (await rows()) >= before + 1)
      expect(added, `import on ${pid} did not add a row (${before} → ${await rows()})`)
      expect(/Imported 1 rows/.test(await noticeText()), `import on ${pid} gave no notice (got "${(await noticeText()).slice(-70)}")`)
    }

    const probePipeline = async (i, pid, roleLabel) => {
      const btns = root(i).locator('.blk-pipe button')
      if ((await btns.count()) === 0) return
      await btns.first().click()
      const moved = await waitFor(async () => /Moved to/.test(await noticeText()), 4000)
      expect(moved, `${roleLabel}: transition on ${pid} gave no notice (got "${(await noticeText()).slice(-70)}")`)
    }

    const probeForm = async (i, pid) => {
      const field = root(i).locator('form.blk-form input:not([type=checkbox]):not([type=hidden]), form.blk-form textarea').first()
      if ((await field.count()) === 0) { fail(`settings form on ${pid} rendered no fields`); return }
      const before = await field.inputValue()
      const next = before ? `${before} ·QA` : 'QA edit'
      await field.fill(next)
      await root(i).locator('form.blk-form').getByRole('button', { name: 'Save', exact: true }).click()
      const saved = await waitFor(async () => /Saved/.test(await noticeText()), 4000)
      expect(saved, `settings form on ${pid} gave no "Saved" notice (got "${(await noticeText()).slice(-70)}")`)
      const other = navFor(spec, role).find((e) => e.pageId !== pid)
      if (other) {
        await navClick(other.label, other.pageId)
        currentPage = other.pageId
        await ensure(pid)
        const after = await root(i).locator('form.blk-form input:not([type=checkbox]):not([type=hidden]), form.blk-form textarea').first().inputValue()
        expect(after === next, `settings form on ${pid} did not persist (got "${after}")`)
      }
    }

    const probeKanbanDrag = async (i, b, pid) => {
      if (!b.props.drag_transitions) return
      const cols = root(i).locator('.blk-col')
      const n = await cols.count()
      if (n < 2) return
      const label = async (j) => (await cols.nth(j).locator('h4').innerText()).replace(/\s*\(\d+\)\s*$/, '').trim()
      const states = []
      for (let j = 0; j < n; j++) states.push(await label(j))
      if ((await cols.nth(0).locator('.blk-card').count()) === 0) return
      const lc = spec.model.entities.find((e) => e.id === b.props.entity)?.lifecycle
      const roleOk = (t) => !(t.roles ?? []).length || t.roles.includes(role)
      // Column headers are displayed upper-cased; lifecycle values keep their
      // spec casing — compare case-insensitively.
      const eq = (a, c) => String(a ?? '').toLowerCase() === String(c ?? '').toLowerCase()
      let targetIdx = -1
      for (let j = 1; j < n; j++) {
        if ((lc?.transitions ?? []).some((t) => eq(t.from, states[0]) && eq(t.to, states[j]) && roleOk(t))) { targetIdx = j; break }
      }
      const expectMove = targetIdx >= 0
      if (targetIdx < 0) targetIdx = 1
      const srcLabel = states[0]
      const targetLabel = states[targetIdx]
      const card = cols.nth(0).locator('.blk-card').first()
      const title = (await card.locator('strong').first().innerText()).trim()
      await root(i).evaluate((el) => el.setAttribute('data-qa-kanban', '1'))
      await card.dragTo(cols.nth(targetIdx)).catch(() => {})
      const colHasCard = (labelWanted, ttl) => root(i).evaluate((el, [lab, t]) => {
        for (const col of el.querySelectorAll('.blk-col')) {
          const h = (col.querySelector('h4')?.textContent ?? '').replace(/\s*\(\d+\)\s*$/, '').trim()
          if (h.toLowerCase() === String(lab).toLowerCase()) return [...col.querySelectorAll('.blk-card')].some((c) => (c.querySelector('strong')?.textContent ?? '').includes(t))
        }
        return false
      }, [labelWanted, ttl])
      let moved = await waitFor(() => colHasCard(targetLabel, title), 1500)
      if (!moved && (await colHasCard(srcLabel, title))) {
        await synthDrag(page, card, cols.nth(targetIdx))
        moved = await waitFor(() => colHasCard(targetLabel, title), 2500)
      }
      const alive = await page.evaluate(() => !!document.querySelector('[data-qa-kanban]'))
      if (!alive) { fail(`kanban drag on ${pid} navigated away instead of dragging`); await ensure(pid); return }
      await waitFor(async () => {
        const n = await noticeText()
        return expectMove ? /Moved to/.test(n) : /No transition into/.test(n)
      }, 3000)
      const nt = await noticeText()
      if (expectMove) {
        expect(moved || /Moved to/.test(nt), `kanban ${srcLabel} → ${targetLabel} on ${pid} did not move (notice "${nt.slice(-60)}")`)
      } else {
        expect(/No transition into/.test(nt), `kanban illegal drop ${srcLabel} → ${targetLabel} on ${pid}: no refusal notice (got "${nt.slice(-60)}")`)
        expect(!moved, `kanban illegal drop ${srcLabel} → ${targetLabel} on ${pid} moved anyway`)
      }
    }

    const probeTableOpen = async (i, b, pid) => {
      if (!b.props.row_link) return
      const row = root(i).locator('.blk-table tbody tr').first()
      if ((await row.count()) === 0) return
      const text = (await row.locator('td').first().innerText()).trim()
      await row.click()
      await settle(350)
      await expectArrived(b.props.row_link, text)
      await ensure(pid)
    }

    const probeRelatedOpen = async (i, b, pid) => {
      if (!b.props.row_link) return
      const li = root(i).locator('.blk-related li').first()
      if ((await li.count()) === 0) return
      const text = (await li.innerText()).trim()
      await li.click()
      await settle(350)
      await expectArrived(b.props.row_link, text)
      await ensure(pid)
    }

    const probeKanbanOpen = async (i, b, pid) => {
      const card = root(i).locator('.blk-card').first()
      if ((await card.count()) === 0) return
      const title = (await card.locator('strong').first().innerText()).trim()
      await card.click()
      await settle(350)
      const target = detailPageFor(spec, b.props.entity)
      if (target) {
        await expectArrived(target, title)
        await ensure(pid)
      } else {
        const modal = page.locator('.blk-modal')
        try { await modal.waitFor({ timeout: 3000 }) } catch { fail(`kanban card click on ${pid} opened nothing`); return }
        const aria = await modal.getAttribute('aria-label')
        expect(/^Edit /.test(aria ?? ''), `kanban card click on ${pid} opened "${aria}" instead of an edit dialog`)
        await modal.getByRole('button', { name: 'Cancel' }).click().catch(() => {})
        await modal.waitFor({ state: 'detached', timeout: 3000 }).catch(() => {})
      }
    }

    const probeCalendarOpen = async (i, b, pid) => {
      const btn = root(i).locator('.blk-day button').first()
      if ((await btn.count()) === 0) return
      const text = (await btn.innerText()).trim()
      await btn.click()
      await settle(350)
      const target = linkTarget(spec, b)
      if (target) await expectArrived(target, text)
      await ensure(pid)
    }

    // ---- default-role walk -----------------------------------------------------
    const visited = new Set()
    const queue = navFor(spec, role).map((e) => e.pageId)
    while (queue.length) {
      const pid = queue.shift()
      if (visited.has(pid)) continue
      visited.add(pid)
      if (!(await ensure(pid))) { fail(`cannot reach page ${pid}`); continue }
      const blocks = pagesById.get(pid).blocks ?? []
      console.log(`   · ${pid} (${blocks.length} blocks)`)
      const rootsN = await roots.count()
      expect(rootsN === blocks.length, `page ${pid} rendered ${rootsN} blocks, spec has ${blocks.length}`)
      for (let i = 0; i < blocks.length; i++) {
        const cls = await root(i).evaluate((el) => el.className).catch(() => '')
        if (cls.includes('blk-error')) fail(`${blocks[i].type} on ${pid} is in error state`)
        else if (cls.includes('blk-empty')) console.log(`   ~ ${blocks[i].type} on ${pid} renders empty (review)`)
      }
      // pass A — non-navigational controls
      for (let i = 0; i < blocks.length; i++) {
        const b = blocks[i]
        if (b.type === 'filter.bar' && b.props.entity) await probeFilter(i, b, pid)
        else if (b.type === 'data.table' && b.props.create) { await probeCreate(i, b, pid, false); await probeExport(i, b, pid); await probeImport(i, b, pid) }
        else if (b.type === 'data.table') { await probeExport(i, b, pid); await probeImport(i, b, pid) }
        else if (b.type === 'record.related_list' && b.props.create) await probeCreate(i, b, pid, true)
        else if (b.type === 'lifecycle.pipeline') await probePipeline(i, pid, `role ${role}`)
        else if (b.type === 'data.kanban') await probeKanbanDrag(i, b, pid)
        else if (b.type === 'form.record') await probeForm(i, pid)
      }
      // pass B — navigational controls
      for (let i = 0; i < blocks.length; i++) {
        const b = blocks[i]
        if (b.type === 'data.table') await probeTableOpen(i, b, pid)
        else if (b.type === 'record.related_list') await probeRelatedOpen(i, b, pid)
        else if (b.type === 'data.kanban') await probeKanbanOpen(i, b, pid)
        else if (b.type === 'calendar.month') await probeCalendarOpen(i, b, pid)
      }
      for (const b of blocks) {
        const t = linkTarget(spec, b)
        if (t && !visited.has(t)) queue.push(t)
      }
    }

    // ---- host chrome: print
    const printBtn = page.getByRole('button', { name: /Print \/ PDF/ })
    if (!(await waitFor(async () => (await printBtn.count()) > 0, 5000))) {
      fail('print bar missing')
    } else {
      await printBtn.click()
      expect(await waitFor(async () => (await page.evaluate(() => window.__printCount)) >= 1, 2000),
        'Print / PDF did not call window.print')
    }

    // ---- other roles: nav walk + their transitions
    for (const r of rolesWant.slice(1)) {
      await roleSel.selectOption(r)
      await waitFor(async () =>
        (await roleSel.inputValue().catch(() => '')) === r && (await roots.first().isVisible().catch(() => false)), 10000)
      role = r
      currentPage = (await activeNavPage()) ?? navFor(spec, r)[0]?.pageId ?? currentPage
      for (const entry of navFor(spec, r)) {
        await navClick(entry.label, entry.pageId)
        currentPage = entry.pageId
        const blocks = pagesById.get(entry.pageId).blocks ?? []
        for (let i = 0; i < blocks.length; i++) {
          const cls = await root(i).evaluate((el) => el.className).catch(() => '')
          if (cls.includes('blk-error')) fail(`${blocks[i].type} on ${entry.pageId} (role ${r}) is in error state`)
        }
        const pi = blocks.findIndex((b) => b.type === 'lifecycle.pipeline')
        const linkIdx = blocks.findIndex((b) => linkTarget(spec, b) !== null)
        if (linkIdx >= 0) {
          const target = linkTarget(spec, blocks[linkIdx])
          const ok = await clickLink(entry.pageId, target)
          if (ok) {
            await settle(350)
            currentPage = target
            const pi2 = (pagesById.get(target).blocks ?? []).findIndex((b) => b.type === 'lifecycle.pipeline')
            if (pi2 >= 0) await probePipeline(pi2, target, `role ${r}`)
            await ensure(entry.pageId)
          }
        } else if (pi >= 0) {
          await probePipeline(pi, entry.pageId, `role ${r}`)
        }
      }
    }

    // ---- host chrome: PIN (once per run — same component in every app)
    if (withPin) {
      await page.getByRole('button', { name: /Set PIN/ }).click()
      await page.locator('input[aria-label="pin"]').fill('1234')
      await page.locator('input[aria-label="confirm pin"]').fill('1234')
      await page.getByRole('button', { name: 'Set PIN', exact: true }).click()
      await settle(400)
      expect(/PIN set on this device/.test(await noticeText()), 'PIN setup gave no notice')
      await page.getByRole('button', { name: /Lock/ }).click()
      await page.locator('input[aria-label="pin"]').waitFor({ timeout: 4000 })
      await page.locator('input[aria-label="pin"]').fill('1234')
      await page.getByRole('button', { name: 'Unlock', exact: true }).click()
      await settle(500)
      expect(await shell.isVisible(), 'PIN unlock did not restore the app')
    }
  } catch (e) {
    fail(`sweep crashed: ${(e.message ?? '').split('\n')[0].slice(0, 150)}`)
    const dbg = await page.evaluate(() => ({
      url: location.pathname + location.hash,
      shells: document.querySelectorAll('.app-shell').length,
      mains: document.querySelectorAll('.app-main').length,
      roots: document.querySelectorAll('.app-main > .blk:not([role="status"])').length,
      text: (document.querySelector('.app-main')?.innerText ?? document.body.innerText).replace(/\s+/g, ' ').slice(0, 140),
    })).catch(() => null)
    if (dbg) console.log(`   · state: ${JSON.stringify(dbg)}`)
    await page.screenshot({ path: path.join(SHOTS, `${appSlug}-crash.png`) }).catch(() => {})
  }

  for (const e of errs) fail(e.slice(0, 200))
  await context.close()
  const mark = issues.length ? '✗' : '✓'
  console.log(` ${mark} ${app}: ${checks} checks, ${issues.length} issues`)
  return { app, checks, issues }
}

// ---- main -------------------------------------------------------------------

const browser = await chromium.launch({ channel: 'chrome' })
console.log(`QA sweep → ${BASE} (${specs.length} apps)`)
const results = []
let first = true
for (const spec of specs) {
  results.push(await qaApp(browser, spec, { withPin: first }))
  first = false
}
await browser.close()

const totalChecks = results.reduce((n, r) => n + r.checks, 0)
const allIssues = results.flatMap((r) => r.issues.map((i) => `${r.app}: ${i}`))
console.log(`\n${'-'.repeat(60)}`)
console.log(`apps: ${results.length} · checks: ${totalChecks} · issues: ${allIssues.length}`)
for (const i of allIssues) console.log(` ✗ ${i}`)
if (allIssues.length) {
  console.log(`\nfailed — screenshots in docs/assets/qa/`)
  process.exit(1)
}
console.log('all interaction checks passed')
