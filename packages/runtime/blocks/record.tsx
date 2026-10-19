/** Record blocks: detail, related list, lifecycle pipeline, create/edit form. */
import React from "react";
import { BlockShell } from "./chrome.tsx";
import { displayPath, resolveState } from "./types.ts";
import type { BlockHostProps, Rec } from "./types.ts";

export function RecordDetail({ block, record, state, error }: BlockHostProps<{
  entity: string; sections?: Array<{ title: string; fields: string[] }>;
}>) {
  const st = resolveState(undefined, record ?? null, state, error);
  return (
    <BlockShell state={st} error={error}>
      {st === "ready" && record ? (
        <div className="blk-detail">
          {(block.props.sections ?? []).map((s) => (
            <div key={s.title}>
              <h4>{s.title}</h4>
              {s.fields.map((f) => (
                <div key={f} className="blk-kv"><span>{f}</span><strong>{displayPath(record, f)}</strong></div>
              ))}
            </div>
          ))}
        </div>
      ) : undefined}
    </BlockShell>
  );
}

export function RelatedList({ block, rows, state, error, onAction }: BlockHostProps<{
  entity: string; via?: string; columns?: string[]; create?: boolean; row_link?: string;
}>) {
  const st = resolveState(rows, undefined, state, error);
  const cols = block.props.columns ?? [];
  const addBtn = block.props.create ? <button onClick={() => onAction?.("create")}>Add</button> : null;
  return (
    <BlockShell state={st} error={error} emptyActions={addBtn ?? undefined}>
      {st === "ready" ? (
        <>
          <ul className="blk-related">
            {(rows ?? []).map((r, i) => (
              <li key={String(r["id"] ?? i)}
                className={block.props.row_link ? "blk-row-link" : undefined}
                onClick={block.props.row_link ? () => onAction?.("open", r["id"]) : undefined}>
                {cols.map((c) => displayPath(r, c)).join(" · ")}
              </li>
            ))}
          </ul>
          {addBtn}
        </>
      ) : undefined}
    </BlockShell>
  );
}

export interface PipeTransition { id: string; label: string; allowed: boolean }

export function LifecyclePipeline({ block, record, state, error, onAction, transitions, current }: BlockHostProps<{
  entity: string;
}> & { transitions?: PipeTransition[]; current?: string }) {
  const st = resolveState(undefined, record ?? null, state, error);
  return (
    <BlockShell state={st} error={error}>
      {st === "ready" ? (
        <div className="blk-pipe">
          {(transitions ?? []).map((t) => (
            <button key={t.id} disabled={!t.allowed}
              className={t.id === current ? "current" : ""}
              onClick={() => onAction?.("transition", t.id)}>
              {t.label}
            </button>
          ))}
        </div>
      ) : undefined}
    </BlockShell>
  );
}

export interface FormFieldDef { id: string; label?: string; type: string; required?: boolean }

export function FormRecord({ block, record, state, error, onAction }: BlockHostProps<{
  entity: string; fields?: FormFieldDef[];
}> & { initial?: Rec }) {
  const st = resolveState(undefined, record === undefined ? undefined : (record ?? null), state, error);
  const initial = (block as { initial?: Rec }).initial ?? record ?? {};
  const [values, setValues] = React.useState<Rec>(initial);
  const set = (k: string, v: unknown) => setValues((prev) => ({ ...prev, [k]: v }));
  return (
    <BlockShell state={st} error={error}>
      {st === "ready" ? (
        <form className="blk-form" onSubmit={(e) => { e.preventDefault(); onAction?.("submit", values); }}>
          {(block.props.fields ?? []).map((f) => (
            <label key={f.id}>{f.label ?? f.id}
              {f.type === "bool" ? (
                <input type="checkbox" checked={!!values[f.id]}
                  onChange={(e) => set(f.id, e.target.checked)} />
              ) : f.type === "longtext" ? (
                <textarea value={String(values[f.id] ?? "")}
                  onChange={(e) => set(f.id, e.target.value)} />
              ) : (
                <input
                  type={f.type === "int" || f.type === "decimal" || f.type === "money" ? "number"
                    : f.type === "date" ? "date" : f.type === "datetime" ? "datetime-local" : "text"}
                  value={String(values[f.id] ?? "")}
                  required={!!f.required}
                  onChange={(e) => set(f.id, f.type === "int" ? parseInt(e.target.value, 10) : e.target.value)} />
              )}
            </label>
          ))}
          <button type="submit">Save</button>
        </form>
      ) : undefined}
    </BlockShell>
  );
}
