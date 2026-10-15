/**
 * RuntimePreview (Phase 6, P6.6): Track A preview — renders an App Spec as
 * data through the runtime (shell + blocks + Dexie adapter), no codegen,
 * no sandbox. Shown in Studio when the wish carries `artifacts.spec_v1`
 * (v2 pipeline output); Sandpack stays for legacy wishes.
 */
import { Suspense, lazy, useEffect, useMemo, useState } from 'react'
import type { AppSpec } from '../../../packages/spec/app-spec.ts'
import { DexieAdapter } from '../../../packages/runtime/adapters/dexie.ts'
import { AppShell } from '../../../packages/runtime/shell/shell.tsx'
import { RoleSession } from '../../../packages/runtime/shell/roles.ts'
import { BLOCK_COMPONENTS } from '../../../packages/runtime/blocks/components.ts'
import { resolveSeed } from '../../../packages/runtime/testing/g3.ts'
import { allowedTransitions, applyTransition } from '../../../packages/runtime/engine/lifecycle.ts'
import { runAutomations } from '../../../packages/runtime/automation/executor.ts'
import { parseCsv, toCsv } from '../../../packages/runtime/blocks/csv.ts'
import { uploadBlob, UPLOAD_BUCKET } from '../../../packages/runtime/storage/uploads.ts';
import { isSupabaseDemo, supabase } from '../supabase';
const RolesMatrix = lazy(() => import('./RolesMatrix').then(m => ({ default: m.RolesMatrix })));

type Rows = Record<string, Array<Record<string, unknown>>>;

export function RuntimePreview({ spec }: { spec: AppSpec }) {
  const adapter = useMemo(() => new DexieAdapter(`intara-preview-${spec.app.name}`), [spec]);
  const [session, setSession] = useState(() => new RoleSession(spec));
  const [activePage, setActivePage] = useState(spec.ui.pages[0]?.id ?? '');
  const [rows, setRows] = useState<Rows>({});
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [ready, setReady] = useState(false);
  const [notices, setNotices] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setReady(false);
      const seed = resolveSeed(spec);
      for (const [ent, rs] of Object.entries(seed)) {
        if ((await adapter.list(ent, {})).total === 0) {
          for (const r of rs) await adapter.put(ent, r);
        }
      }
      const all: Rows = {};
      for (const e of spec.model.entities) all[e.id] = (await adapter.list(e.id, {})).rows as Rows[string];
      if (!cancelled) {
        setRows(all);
        setSelected(null);
        if (!spec.ui.pages.some((p) => p.id === activePage)) setActivePage(spec.ui.pages[0]?.id ?? '');
        setReady(true);
      }
    })().catch((e) => console.error('runtime preview failed', e));
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [adapter, spec, session.current]);

  async function refresh() {
    const all: Rows = {};
    for (const e of spec.model.entities) all[e.id] = (await adapter.list(e.id, {})).rows as Rows[string];
    setRows(all);
  }

  const page = spec.ui.pages.find((p) => p.id === activePage) ?? spec.ui.pages[0];
  if (!ready || !page) return <div className="glass" style={{ padding: 28, textAlign: 'center' }}>Loading app…</div>;

  async function fireAutomations(type: 'record.created' | 'lifecycle.transition', entity: string, record: Record<string, unknown>, extra?: { transition?: string }) {
    try {
      const fx = await runAutomations(spec, adapter, { type, entity, record, ...extra });
      const msgs = fx.filter((e) => e.kind === 'notify' || e.kind === 'deferred').map((e) => e.detail);
      if (msgs.length) setNotices((prev) => [...msgs, ...prev].slice(0, 5));
      if (fx.some((e) => e.kind === 'set_field' || e.kind === 'create_record')) await refresh();
    } catch (e) {
      console.error('automation failed', e);
    }
  }

  async function onAction(blockType: string, props: Record<string, unknown>, action: string, payload?: unknown) {
    const entity = props['entity'] as string | undefined;
    if (!entity) return;
    if (action === 'transition' && selected && typeof payload === 'string') {
      const next = applyTransition(spec, entity, selected, payload, { role: session.current });
      await adapter.put(entity, next);
      setSelected(next);
      await refresh();
      await fireAutomations('lifecycle.transition', entity, next, { transition: payload });
    } else if (action === 'submit' && payload && typeof payload === 'object') {
      const saved = await adapter.put(entity, payload as Record<string, unknown>);
      await refresh();
      await fireAutomations('record.created', entity, saved);
    } else if (action === 'open') {
      const rec = (rows[entity] ?? []).find((r) => String(r['id']) === String(payload)) ?? null;
      setSelected(rec);
    } else if (action === 'move' && payload && typeof payload === 'object') {
      // kanban drag: resolve the lifecycle transition into the target column
      const { id, to } = payload as { id?: unknown; to?: unknown };
      const rec = (rows[entity] ?? []).find((r) => String(r['id']) === String(id));
      if (rec && typeof to === 'string') {
        const t = allowedTransitions(spec, entity, rec, { role: session.current })
          .find((x) => x.to === to);
        if (t) {
          const next = applyTransition(spec, entity, rec, t.id, { role: session.current });
          await adapter.put(entity, next);
          setSelected(next);
          await refresh();
          await fireAutomations('lifecycle.transition', entity, next, { transition: t.id });
        } else {
          setNotices((prev) => [`No transition into '${to}' from here.`].concat(prev).slice(0, 5));
        }
      }
    } else if (action === 'export') {
      const csv = toCsv(rows[entity] ?? []);
      const blob = new Blob([csv], { type: 'text/csv' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `${entity}.csv`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    } else if (action === 'import' && payload && typeof payload === 'object') {
      const text = (payload as { text?: unknown }).text;
      if (typeof text === 'string') {
        const parsed = parseCsv(text);
        for (const r of parsed) await adapter.put(entity, r);
        await refresh();
        setNotices((prev) => [`Imported ${parsed.length} rows into ${entity}.`].concat(prev).slice(0, 5));
      }
    } else if (action === 'upload' && payload && typeof payload === 'object') {
      const { file, filename, field } = payload as { file?: unknown; filename?: unknown; field?: unknown };
      if (file instanceof Blob && typeof filename === 'string') {
        if (isSupabaseDemo) {
          setNotices((prev) => ['Uploads need Supabase (connect in trial settings).'].concat(prev).slice(0, 5));
        } else {
          const url = await uploadBlob(supabase as never, entity, filename, file);
          await adapter.put(entity, { [typeof field === 'string' ? field : 'file']: url });
          await refresh();
          setNotices((prev) => [`Uploaded to ${UPLOAD_BUCKET}.`].concat(prev).slice(0, 5));
        }
      }
    }
  }

  return (
    <>
      <style>{`@media print {
        .intara-nav, .blk-actions, .blk-printbar, button, input, select { display: none !important; }
        .intara-shell, .intara-main, .blk { background: #fff !important; color: #000 !important; }
        .blk-card, .blk-day { break-inside: avoid; }
      }`}</style>
      <div className="blk-printbar" style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <button className="btn-ghost btn-sm" onClick={() => window.print()}>🖨 Print / PDF</button>
      </div>
      <Suspense fallback={null}>
        <RolesMatrix spec={spec} current={session.current} />
      </Suspense>
      <AppShell
      spec={spec}
      session={session}
      activePage={page.id}
      onNavigate={(id) => { setActivePage(id); setSelected(null); }}
      onRole={(role) => { const next = new RoleSession(spec, role); next.switch(role); setSession(next); }}
    >
      {notices.length > 0 && (
        <div className="blk" role="status" style={{ marginBottom: 8 }}>
          {notices.map((n, i) => <div key={i} style={{ fontSize: 12 }}>🔔 {n}</div>)}
        </div>
      )}
      {(page.blocks ?? []).map((b) => {
        const C = BLOCK_COMPONENTS[b.type];
        if (!C) return <div key={b.id} className="glass" style={{ padding: 12 }}>Unknown block {b.type}</div>;
        const props = { ...(b.props as Record<string, unknown>) };
        const entity = props['entity'] as string | undefined;
        let record: Record<string, unknown> | null | undefined;
        let pipe: { transitions: Array<{ id: string; label: string; allowed: boolean }>; current: string } | null = null;
        if (b.type === 'record.detail' || b.type === 'lifecycle.pipeline') {
          record = selected ?? (entity ? (rows[entity] ?? [])[0] ?? null : null);
          if (b.type === 'lifecycle.pipeline' && entity && record) {
            const ent = spec.model.entities.find((e) => e.id === entity)!;
            const field = ent.lifecycle?.field ?? 'status';
            pipe = {
              transitions: allowedTransitions(spec, entity, record, { role: session.current })
                .map((t) => ({ id: t.id, label: t.label, allowed: true })),
              current: String(record[field] ?? ''),
            };
          }
        }
        if (b.type === 'form.record' && entity) record = selected ?? undefined;
        return (
          <C key={b.id}
            block={{ id: b.id, type: b.type, props }}
            rows={entity ? rows[entity] : undefined}
            record={record}
            {...(pipe ?? {})}
            onAction={(a, p) => { onAction(b.type, props, a, p).catch((e) => console.error(e)); }}
          />
        );
      })}
    </AppShell>
    </>
  );
}
