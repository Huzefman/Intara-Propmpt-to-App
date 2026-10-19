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
import { navForRole } from '../../../packages/runtime/shell/nav.ts'
import { BLOCK_COMPONENTS } from '../../../packages/runtime/blocks/components.ts'
import { resolveSeed } from '../../../packages/runtime/testing/g3.ts'
import { computeRecord } from '../../../packages/runtime/engine/computed.ts'
import { allowedTransitions, applyTransition } from '../../../packages/runtime/engine/lifecycle.ts'
import { runAutomations } from '../../../packages/runtime/automation/executor.ts'
import { parseCsv, toCsv } from '../../../packages/runtime/blocks/csv.ts'
import { uploadBlob, UPLOAD_BUCKET } from '../../../packages/runtime/storage/uploads.ts';
import { enrollPin, isEnrolled, verifyPin } from '../../../packages/runtime/auth/pin.ts';
import { isSupabaseDemo, supabase } from '../supabase';
import { CreateDialog } from './CreateDialog';
const RolesMatrix = lazy(() => import('./RolesMatrix').then(m => ({ default: m.RolesMatrix })));
const PinGate = lazy(() => import('../../../packages/runtime/shell/PinGate.tsx').then(m => ({ default: m.PinGate })));

type Rows = Record<string, Array<Record<string, unknown>>>;

/** Text of a (possibly hydrated-ref, possibly dotted-path) cell — for
 * client-side filtering. */
function cellText(r: Record<string, unknown>, k: string): string {
  const parts = k.split('.');
  let v: unknown = r[parts[0]];
  for (let i = 1; i < parts.length && v && typeof v === 'object' && !Array.isArray(v); i++) {
    v = (v as Record<string, unknown>)[parts[i]];
  }
  if (v && typeof v === 'object' && !Array.isArray(v)) {
    const rec = v as Record<string, unknown>;
    for (const p of ['name', 'title', 'first_name', 'label']) {
      const s = rec[p];
      if (typeof s === 'string' && s) return s;
    }
    return '';
  }
  if (Array.isArray(v)) {
    return v.map((x) => (x && typeof x === 'object' ? String((x as Record<string, unknown>)['name'] ?? '') : String(x))).join(' ');
  }
  return String(v ?? '');
}

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
  const refFields = (entityId: string) => (spec.model.entities.find((e) => e.id === entityId)?.fields ?? [])
    .filter((f) => (f.type === 'ref' || f.type === 'multi_ref') && f.target);
  const cache = new Map<string, Record<string, unknown>>();
  const building = new Set<string>();
  // Resolve refs recursively (memoized, cycle-safe): dotted paths two levels
  // deep — `planting.plant.common_name` — need a hydrated target whose own
  // refs are hydrated too.
  const hydrate = (entityId: string, r: Record<string, unknown>): Record<string, unknown> => {
    const key = `${entityId}:${String(r['id'])}`;
    const hit = cache.get(key);
    if (hit) return hit;
    if (building.has(key)) return r; // ref cycle: fall back to the raw row
    building.add(key);
    let copy = r;
    for (const f of refFields(entityId)) {
      const v = r[f.id];
      if (typeof v === 'string') {
        const t = byId[f.target as string]?.get(v);
        if (t) {
          if (copy === r) copy = { ...r };
          copy[f.id] = hydrate(f.target as string, t);
        }
      } else if (Array.isArray(v) && f.type === 'multi_ref') {
        if (copy === r) copy = { ...r };
        copy[f.id] = v.map((id) => {
          const t = byId[f.target as string]?.get(String(id));
          return t ? hydrate(f.target as string, t) : id;
        });
      }
    }
    building.delete(key);
    cache.set(key, copy);
    return copy;
  };
  const out: Rows = {};
  for (const e of spec.model.entities) out[e.id] = (rows[e.id] ?? []).map((r) => hydrate(e.id, r));
  return out;
}

export function RuntimePreview({ spec }: { spec: AppSpec }) {
  const adapter = useMemo(() => new DexieAdapter(`intara-preview-${spec.app.name}`), [spec]);
  const [session, setSession] = useState(() => new RoleSession(spec));
  const [activePage, setActivePage] = useState(spec.ui.pages[0]?.id ?? '');
  const [rows, setRows] = useState<Rows>({});
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [selectedEntity, setSelectedEntity] = useState<string | null>(null);
  const [creating, setCreating] = useState<{ entity: string; via?: string } | null>(null);
  const [editing, setEditing] = useState<{ entity: string; record: Record<string, unknown> } | null>(null);
  const [filters, setFilters] = useState<Record<string, Record<string, { q?: string; search?: string[]; fields: Record<string, string> }>>>({});
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

  async function fireAutomations(type: 'record.created' | 'record.updated' | 'lifecycle.transition', entity: string, record: Record<string, unknown>, extra?: { transition?: string }) {
    try {
      const fx = await runAutomations(spec, adapter, { type, entity, record, ...extra });
      const msgs = fx.filter((e) => e.kind === 'notify' || e.kind === 'deferred').map((e) => e.detail);
      if (msgs.length) setNotices((prev) => [...msgs, ...prev].slice(0, 5));
      if (fx.some((e) => e.kind === 'set_field' || e.kind === 'create_record')) await refresh();
    } catch (e) {
      console.error('automation failed', e);
    }
  }

  /** Persist a record through the adapter: create or update, firing the right
   * automation event, selecting the saved row, and leaving a visible notice. */
  async function saveRecord(entity: string, values: Record<string, unknown>) {
    const ent = spec.model.entities.find((e) => e.id === entity);
    // a fresh record has no related rows yet, so evaluate with empty related
    const rec = ent ? computeRecord(ent, values, {}).record : values;
    const isUpdate = typeof rec['id'] === 'string' && (rows[entity] ?? []).some((r) => String(r['id']) === String(rec['id']));
    const saved = await adapter.put(entity, rec);
    await refresh();
    await fireAutomations(isUpdate ? 'record.updated' : 'record.created', entity, saved);
    // Follow the saved record into `selected` — but never clobber the parent
    // context when a child is saved from a related list (its Add dialog
    // prefills `via` from the selection).
    if (selectedEntity === entity || selectedEntity === null) {
      setSelected(saved);
      setSelectedEntity(entity);
    }
    setNotices((prev) => [`${isUpdate ? 'Saved' : 'Created'} ${ent?.label ?? entity}.`].concat(prev).slice(0, 5));
  }

  /** Table/board/calendar/list `open`: select the record and jump to the page
   * that can show it (explicit row_link first, else the entity's detail page).
   * When the spec has no detail page at all (e.g. a pipeline-only app), open
   * the record for editing so card clicks still do something useful. */
  function openRecord(entity: string, props: Record<string, unknown>, id: unknown) {
    const rec = (rows[entity] ?? []).find((r) => String(r['id']) === String(id)) ?? null;
    setSelected(rec);
    setSelectedEntity(entity);
    const explicit = typeof props['row_link'] === 'string'
      ? spec.ui.pages.find((p) => p.id === props['row_link']) : undefined;
    const detail = explicit ?? spec.ui.pages.find((p) =>
      (p.blocks ?? []).some((b) => b.type === 'record.detail'
        && (b.props as Record<string, unknown> | undefined)?.['entity'] === entity));
    if (detail) {
      if (detail.id !== page.id) setActivePage(detail.id);
    } else if (rec) {
      setEditing({ entity, record: rec });
    }
  }

  async function onAction(blockType: string, props: Record<string, unknown>, action: string, payload?: unknown) {
    const entity = props['entity'] as string | undefined;
    if (!entity) return;
    if (action === 'transition' && selected && typeof payload === 'string') {
      const next = applyTransition(spec, entity, selected, payload, { role: session.current });
      await adapter.put(entity, next);
      setSelected(next);
      setSelectedEntity(entity);
      await refresh();
      await fireAutomations('lifecycle.transition', entity, next, { transition: payload });
      const field = spec.model.entities.find((e) => e.id === entity)?.lifecycle?.field;
      if (field) setNotices((prev) => [`Moved to '${String(next[field])}'.`].concat(prev).slice(0, 5));
    } else if (action === 'submit' && payload && typeof payload === 'object') {
      await saveRecord(entity, payload as Record<string, unknown>);
    } else if (action === 'open') {
      openRecord(entity, props, payload);
    } else if (action === 'create') {
      setCreating({ entity, via: typeof props['via'] === 'string' ? props['via'] : undefined });
    } else if (action === 'search') {
      setFilters((prev) => ({
        ...prev,
        [page.id]: {
          ...(prev[page.id] ?? {}),
          [entity]: {
            ...(prev[page.id]?.[entity] ?? { fields: {} }),
            q: String(payload ?? ''),
            search: Array.isArray(props['search']) ? (props['search'] as string[]) : undefined,
          },
        },
      }));
    } else if (action === 'filter' && payload && typeof payload === 'object') {
      setFilters((prev) => ({
        ...prev,
        [page.id]: {
          ...(prev[page.id] ?? {}),
          [entity]: {
            ...(prev[page.id]?.[entity] ?? { fields: {} }),
            fields: { ...(prev[page.id]?.[entity]?.fields ?? {}), ...(payload as Record<string, string>) },
          },
        },
      }));
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
          setSelectedEntity(entity);
          await refresh();
          await fireAutomations('lifecycle.transition', entity, next, { transition: t.id });
          const field = spec.model.entities.find((e) => e.id === entity)?.lifecycle?.field;
          if (field) setNotices((prev) => [`Moved to '${String(next[field])}'.`].concat(prev).slice(0, 5));
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

  /** Client-side filter state (FilterBar search + field filters), keyed by
   * page + entity so a query can stack with field selections. */
  function applyFilters(entity: string, rws: Rows[string]): Rows[string] {
    const f = filters[page.id]?.[entity];
    if (!f) return rws;
    const q = (f.q ?? '').trim().toLowerCase();
    const fieldFilters = Object.entries(f.fields ?? {}).filter(([, v]) => String(v ?? '').trim() !== '');
    if (!q && !fieldFilters.length) return rws;
    return rws.filter((r) => {
      if (q) {
        const keys = f.search && f.search.length ? f.search : Object.keys(r);
        if (!keys.some((k) => cellText(r, k).toLowerCase().includes(q))) return false;
      }
      for (const [k, v] of fieldFilters) {
        if (!cellText(r, k).toLowerCase().includes(String(v).toLowerCase())) return false;
      }
      return true;
    });
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
      onNavigate={(id) => {
        setActivePage(id);
        setSelected(null);
        setSelectedEntity(null);
        setFilters((f) => ({ ...f, [id]: {} }));
      }}
      onRole={(role) => {
        const next = new RoleSession(spec, role); next.switch(role); setSession(next);
        // The active page may be invisible to the new role: fall back to its
        // first visible nav page so the preview never shows a forbidden page.
        const visible = navForRole(spec, role);
        if (!visible.some((e) => e.pageId === page.id)) {
          setActivePage(visible[0]?.pageId ?? spec.ui.pages[0]?.id ?? '');
          setSelected(null);
          setSelectedEntity(null);
        }
      }}
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
        // A settings form may omit `fields` (spec registry marks it optional):
        // fall back to every writable field of the entity.
        if (b.type === 'form.record' && entity && !props['fields']) {
          const ent = spec.model.entities.find((e) => e.id === entity);
          props['fields'] = (ent?.fields ?? [])
            .filter((f) => !f.computed)
            .map((f) => ({ id: f.id, label: f.id.replace(/_/g, ' '), type: f.type, required: f.required }));
        }
        // Filtered rows for this block; related lists additionally narrow to
        // the parent record in context (the facing detail / selection).
        let blockRows: Rows[string] | undefined = entity ? applyFilters(entity, viewRows[entity] ?? []) : undefined;
        if (b.type === 'record.related_list' && entity) {
          const childEnt = spec.model.entities.find((e) => e.id === entity);
          const linkField = childEnt?.fields.find((f) => f.id === props['via'] && (f.type === 'ref' || f.type === 'multi_ref'));
          if (linkField?.target) {
            const parent = selected && selectedEntity === linkField.target
              ? selected
              : ((viewRows[linkField.target] ?? [])[0] ?? null);
            if (parent) {
              const relIds = (r: Record<string, unknown>): Array<string> => {
                const v = r[linkField.id];
                if (Array.isArray(v)) {
                  return v.map((x) => (x && typeof x === 'object' ? String((x as Record<string, unknown>)['id'] ?? '') : String(x ?? '')));
                }
                return [v && typeof v === 'object' ? String((v as Record<string, unknown>)['id'] ?? '') : String(v ?? '')];
              };
              blockRows = (blockRows ?? []).filter((r) => relIds(r).includes(String(parent['id'])));
            }
          }
        }
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
        if (b.type === 'form.record' && entity) record = selected ?? (rows[entity] ?? [])[0] ?? undefined;
        return (
          <C key={b.id}
            block={{ id: b.id, type: b.type, props }}
            rows={blockRows}
            record={record}
            {...(pipe ?? {})}
            onAction={(a, p) => { onAction(b.type, props, a, p).catch((e) => console.error(e)); }}
          />
        );
      })}
    </AppShell>
    {(creating || editing) && (() => {
      const target = creating
        ? { entity: creating.entity, via: creating.via, mode: 'create' as const, base: {} as Record<string, unknown> }
        : { entity: editing!.entity, via: undefined as string | undefined, mode: 'edit' as const, base: editing!.record };
      const ent = spec.model.entities.find((e) => e.id === target.entity);
      if (!ent) return null;
      const defaults: Record<string, unknown> = { ...target.base };
      if (target.mode === 'create' && selected && selectedEntity) {
        for (const f of ent.fields) {
          if ((f.type === 'ref' || f.type === 'multi_ref') && f.target === selectedEntity
            && (!target.via || f.id === target.via)) {
            defaults[f.id] = f.type === 'multi_ref' ? [selected['id']] : selected['id'];
          }
        }
      }
      const close = () => { setCreating(null); setEditing(null); };
      return (
        <CreateDialog spec={spec} entity={ent} rows={viewRows} defaults={defaults} mode={target.mode}
          onCancel={close}
          onSubmit={(values) => {
            close();
            saveRecord(target.entity, values).catch((e) => console.error('save failed', e));
          }} />
      );
    })()}
    </>
  );
}
