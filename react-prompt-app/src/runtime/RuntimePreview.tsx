/**
 * RuntimePreview (Phase 6, P6.6): Track A preview — renders an App Spec as
 * data through the runtime (shell + blocks + Dexie adapter), no codegen,
 * no sandbox. Shown in Studio when the wish carries `artifacts.spec_v1`
 * (v2 pipeline output); Sandpack stays for legacy wishes.
 */
import { useEffect, useMemo, useState } from 'react'
import type { AppSpec } from '../../../packages/spec/app-spec.ts'
import { DexieAdapter } from '../../../packages/runtime/adapters/dexie.ts'
import { AppShell } from '../../../packages/runtime/shell/shell.tsx'
import { RoleSession } from '../../../packages/runtime/shell/roles.ts'
import { BLOCK_COMPONENTS } from '../../../packages/runtime/blocks/components.ts'
import { resolveSeed } from '../../../packages/runtime/testing/g3.ts'
import { allowedTransitions, applyTransition } from '../../../packages/runtime/engine/lifecycle.ts'

type Rows = Record<string, Array<Record<string, unknown>>>;

export function RuntimePreview({ spec }: { spec: AppSpec }) {
  const adapter = useMemo(() => new DexieAdapter(`intara-preview-${spec.app.name}`), [spec]);
  const [session, setSession] = useState(() => new RoleSession(spec));
  const [activePage, setActivePage] = useState(spec.ui.pages[0]?.id ?? '');
  const [rows, setRows] = useState<Rows>({});
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [ready, setReady] = useState(false);

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

  async function onAction(blockType: string, props: Record<string, unknown>, action: string, payload?: unknown) {
    const entity = props['entity'] as string | undefined;
    if (!entity) return;
    if (action === 'transition' && selected && typeof payload === 'string') {
      const next = applyTransition(spec, entity, selected, payload, { role: session.current });
      await adapter.put(entity, next);
      setSelected(next);
      await refresh();
    } else if (action === 'submit' && payload && typeof payload === 'object') {
      await adapter.put(entity, payload as Record<string, unknown>);
      await refresh();
    } else if (action === 'open') {
      const rec = (rows[entity] ?? []).find((r) => String(r['id']) === String(payload)) ?? null;
      setSelected(rec);
    }
  }

  return (
    <AppShell
      spec={spec}
      session={session}
      activePage={page.id}
      onNavigate={(id) => { setActivePage(id); setSelected(null); }}
      onRole={(role) => { const next = new RoleSession(spec, role); next.switch(role); setSession(next); }}
    >
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
  );
}
