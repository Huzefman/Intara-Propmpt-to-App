/** Data blocks: table, kanban, filter bar. */
import React from "react";
import { BlockShell } from "./chrome.tsx";
import { displayPath, resolveState } from "./types.ts";
import type { BlockHostProps, Rec } from "./types.ts";

export function DataTable({ block, rows, state, error, onAction }: BlockHostProps<{ entity: string; columns?: string[]; create?: boolean; row_link?: string }>) {
  const st = resolveState(rows, undefined, state, error);
  const cols = block.props.columns ?? [];
  const importRef = React.useRef<HTMLInputElement>(null);
  const actions = (
    <div className="blk-actions">
      {block.props.create ? <button onClick={() => onAction?.("create")}>New</button> : null}
      <button onClick={() => onAction?.("export")}>Export CSV</button>
      <button onClick={() => importRef.current?.click()}>Import CSV</button>
      <input ref={importRef} type="file" accept=".csv,text/csv" hidden
        onChange={async (e) => {
          const f = e.target.files?.[0];
          if (f) onAction?.("import", { text: await f.text(), filename: f.name });
          e.target.value = "";
        }} />
    </div>
  );
  return (
    <BlockShell state={st} error={error} emptyActions={block.props.create ? actions : undefined}>
      {st === "ready" ? (
        <>
          <table className="blk-table">
            <thead><tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
            <tbody>
              {(rows ?? []).map((r, i) => (
                <tr key={String(r["id"] ?? i)}
                  className={block.props.row_link ? "blk-row-link" : undefined}
                  onClick={block.props.row_link ? () => onAction?.("open", r["id"]) : undefined}>
                  {cols.map((c) => <td key={c}>{displayPath(r, c)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
          {actions}
        </>
      ) : undefined}
    </BlockShell>
  );
}

export function Kanban({ block, rows, state, error, onAction }: BlockHostProps<{
  entity: string; group_by: string; card?: { title?: string; subtitle?: string; badges?: string[] }; drag_transitions?: boolean;
}>) {
  const st = resolveState(rows, undefined, state, error);
  const groups = new Map<string, Rec[]>();
  for (const r of rows ?? []) {
    const k = String(r[block.props.group_by] ?? "—");
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k)!.push(r);
  }
  const card = block.props.card ?? {};
  return (
    <BlockShell state={st} error={error}>
      {st === "ready" ? (
        <div className="blk-kanban">
          {[...groups.entries()].map(([g, rs]) => (
            <div key={g} className="blk-col"
              onDragOver={block.props.drag_transitions ? (e) => e.preventDefault() : undefined}
              onDrop={block.props.drag_transitions ? (e) => {
                e.preventDefault();
                try {
                  const data = JSON.parse(e.dataTransfer.getData("text/intara-card"));
                  if (data && data.id !== undefined && data.from !== g)
                    onAction?.("move", { id: data.id, to: g });
                } catch { /* bad payload: ignore */ }
              } : undefined}>
              <h4>{g} ({rs.length})</h4>
              {rs.map((r, i) => (
                <div key={String(r["id"] ?? i)} className="blk-card"
                  draggable={!!block.props.drag_transitions}
                  onDragStart={block.props.drag_transitions ? (e) => {
                    e.dataTransfer.setData("text/intara-card",
                      JSON.stringify({ id: r["id"], from: g }));
                  } : undefined}
                  onClick={() => onAction?.("open", r["id"])}>
                  <strong>{card.title ? displayPath(r, card.title) : "—"}</strong>
                  {card.subtitle ? <span>{displayPath(r, card.subtitle)}</span> : null}
                  {(card.badges ?? []).map((b) => <em key={b}>{displayPath(r, b)}</em>)}
                </div>
              ))}
            </div>
          ))}
        </div>
      ) : undefined}
    </BlockShell>
  );
}

export function FilterBar({ block, state, error, onAction }: BlockHostProps<{
  entity: string; fields?: string[]; search?: string[];
}>) {
  const st = error ? "error" : (state ?? "ready");
  const [q, setQ] = React.useState("");
  return (
    <BlockShell state={st} error={error}>
      {st === "ready" ? (
        <div className="blk-filter">
          <input aria-label="search" value={q}
            placeholder={`Search ${(block.props.search ?? []).join(", ")}`}
            onChange={(e) => { setQ(e.target.value); onAction?.("search", e.target.value); }} />
          {(block.props.fields ?? []).map((f) => (
            <input key={f} aria-label={f} placeholder={f}
              onChange={(e) => onAction?.("filter", { [f]: e.target.value })} />
          ))}
        </div>
      ) : undefined}
    </BlockShell>
  );
}
