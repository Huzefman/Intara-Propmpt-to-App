/**
 * RuntimePreview (Phase 6, P6.6): Track A preview — renders an App Spec as
 * data through the runtime (shell + blocks + Dexie adapter), no codegen,
 * no sandbox. Shown in Studio when the wish carries `artifacts.spec_v1`
 * (v2 pipeline output); Sandpack stays for legacy wishes.
 */
import { Suspense, lazy, useEffect, useMemo, useState } from 'react'
import type { AppSpec } from '../../../packages/spec/app-spec.ts'
import '../../../packages/runtime/blocks/blocks.css'
import { DexieAdapter } from '../../../packages/runtime/adapters/dexie.ts'
import { AppShell } from '../../../packages/runtime/shell/shell.tsx'
import { RoleSession } from '../../../packages/runtime/shell/roles.ts'
import { BLOCK_COMPONENTS } from '../../../packages/runtime/blocks/components.ts'
import { resolveSeed } from '../../../packages/runtime/testing/g3.ts'
import { computeRecord } from '../../../packages/runtime/engine/computed.ts'
import { allowedTransitions, applyTransition } from '../../../packages/runtime/engine/lifecycle.ts'
import { runAutomations } from '../../../packages/runtime/automation/executor.ts'
import { parseCsv, toCsv } from '../../../packages/runtime/blocks/csv.ts'
import { uploadBlob, UPLOAD_BUCKET } from '../../../packages/runtime/storage/uploads.ts';
import { enrollPin, isEnrolled, verifyPin } from '../../../packages/runtime/auth/pin.ts';
import { isSupabaseDemo, supabase } from '../supabase';
const RolesMatrix = lazy(() => import('./RolesMatrix').then(m => ({ default: m.RolesMatrix })));
const PinGate = lazy(() => import('../../../packages/runtime/shell/PinGate.tsx').then(m => ({ default: m.PinGate })));

type Rows = Record<string, Array<Record<string, unknown>>>;

/** Reverse relations for one record: relation_name → rows of the entities
 * whose ref fields target this entity and point back at this record (the
 * engine's per-record `related` contract — see engine.test.ts computed). */
function relatedForRecord(spec: AppSpec, source: Rows, entityId: string, record: Record<string, unknown>): Record<string, unknown[]> {
  const rel: Record<string, unknown[]> = {};
  for (const e of spec.model.entities) {
    for (const f of e.fields) {
      if ((f.type === 'ref' || f.type === 'multi_ref') && f.target === entityId && f.relation_name) {
        rel[f.relation_name] = (source[e.id] ?? []).filter((r) => {
          const v = r[f.id];
          return f.type === 'ref' ? v === record['id'] : Array.isArray(v) && v.includes(record['id']);
        });
      }
    }
  }
  return rel;
}

/** Display view of rows: ref ids hydrated to the target row (dotted paths
 * like `patient.name` resolve; bare ref columns fall back to a label). Raw
 * rows stay untouched for forms, exports and transitions. */
function hydrateRefs(spec: AppSpec, rows: Rows): Rows {
  const byId: Record<string, Map<string, Record<string, unknown>>> = {};
  for (const e of spec.model.entities)
    byId[e.id] = new Map((rows[e.id] ?? []).map((r) => [String(r['id']), r]));
  const out: Rows = {};
  for (const e of spec.model.entities) {
    out[e.id] = (rows[e.id] ?? []).map((r) => {
      let copy = r;
      for (const f of e.fields) {
        if ((f.type === 'ref' || f.type === 'multi_ref') && f.target) {
          const v = r[f.id];
          if (typeof v === 'string' && byId[f.target]?.has(v)) {
            if (copy === r) copy = { ...r };
            copy[f.id] = byId[f.target].get(v);
          } else if (Array.isArray(v) && f.type === 'multi_ref') {
            if (copy === r) copy = { ...r };
            copy[f.id] = v.map((id) => byId[f.target as string]?.get(String(id)) ?? id);
          }
        }
      }
      return copy;
    });
  }
  return out;
}

export function RuntimePreview({ spec }: { spec: AppSpec }) {
  const adapter = useMemo(() => new DexieAdapter(`intara-preview-${spec.app.name}`), [spec]);
  const [session, setSession] = useState(() => new RoleSession(spec));
  const [activePage, setActivePage] = useState(spec.ui.pages[0]?.id ?? '');
  const [rows, setRows] = useState<Rows>({});
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [ready, setReady] = useState(false);
  const [notices, setNotices] = useState<string[]>([]);
  const [pinView, setPinView] = useState<null | 'setup' | 'lock'>(null);
  const [unlocked, setUnlocked] = useState(false);
  const [pinError, setPinError] = useState<string | null>(null);
  const viewRows = useMemo(() => hydrateRefs(spec, rows), [rows, spec]);

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
      // Fill computed fields on seed rows (leaves first, then per-record
      // reverse relations) and persist the diffs so tables/charts show
      // real values instead of em dashes.
      const leaves: Rows = {};
      for (const e of spec.model.entities) leaves[e.id] = all[e.id].map((r) => computeRecord(e, r, {}).record);
      for (const e of spec.model.entities) {
        const raw = all[e.id];
        const next = raw.map((r, i) => computeRecord(e, r, relatedForRecord(spec, leaves, e.id, leaves[e.id][i])).record);
        for (let i = 0; i < next.length; i++) {
          if (JSON.stringify(next[i]) !== JSON.stringify(raw[i])) await adapter.put(e.id, next[i]);
        }
        all[e.id] = next;
      }
      if (!cancelled) {
        setRows(all);
        setSelected(null);
        if (!spec.ui.pages.some((p) => p.id === activePage)) setActivePage(spec.ui.pages[0]?.id ?? '');
        try {
          if (await isEnrolled(adapter)) setPinView((v) => v ?? 'lock');
        } catch { /* auth store unavailable: stay open */ }
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
  if (pinView === 'lock' && !unlocked) {
    return (
      <Suspense fallback={null}>
        <PinGate mode="lock" error={pinError} onSubmit={async (pin) => {
          try {
            if (!(await verifyPin(adapter, pin))) { setPinError('Wrong PIN — try again.'); return; }
            setPinError(null);
            setUnlocked(true);
            setPinView(null);
          } catch (e: any) {
            setPinError(e?.message || 'PIN failed.');
          }
        }} />
      </Suspense>
    );
  }

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
      const ent = spec.model.entities.find((e) => e.id === entity);
      // a fresh record has no related rows yet, so evaluate with empty related
      const rec = ent ? computeRecord(ent, payload as Record<string, unknown>, {}).record : (payload as Record<string, unknown>);
      const saved = await adapter.put(entity, rec);
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
        .app-nav, .blk-actions, .blk-printbar, button, input, select { display: none !important; }
        .app-shell, .app-main, .blk { background: #fff !important; color: #000 !important; }
        .blk-card, .blk-day { break-inside: avoid; }
      }`}</style>
      <div className="blk-printbar" style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <button className="btn-ghost btn-sm" onClick={() => window.print()}>🖨 Print / PDF</button>
        {unlocked
          ? <button className="btn-ghost btn-sm" onClick={() => { setUnlocked(false); setPinView('lock'); }}>🔒 Lock</button>
          : <button className="btn-ghost btn-sm" onClick={() => { setPinError(null); setPinView('setup'); }}>🔑 Set PIN</button>}
      </div>
      {pinView === 'setup' && (
        <Suspense fallback={null}>
          <PinGate mode="setup" error={pinError} onSubmit={async (pin) => {
            try {
              await enrollPin(adapter, pin);
              setNotices((prev) => ['PIN set on this device.'].concat(prev).slice(0, 5));
              setPinError(null);
              setUnlocked(true);
              setPinView(null);
            } catch (e: any) {
              setPinError(e?.message || 'PIN failed.');
            }
          }} />
        </Suspense>
      )}
      {(!pinView || unlocked) && (
      <Suspense fallback={null}>
        <RolesMatrix spec={spec} current={session.current} />
      </Suspense>
      )}
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
          if (b.type === 'record.detail' && entity && record) {
            const facing = (viewRows[entity] ?? []).find((r) => String(r['id']) === String(record!['id']));
            if (facing) record = facing;
          }
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
            rows={entity ? viewRows[entity] : undefined}
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
