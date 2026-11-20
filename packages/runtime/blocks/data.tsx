/** Data blocks: table, kanban, filter bar. */
import React from "react";
import { BlockShell } from "./chrome.tsx";
import { displayPath, resolveState } from "./types.ts";
import type { BlockHostProps, Rec } from "./types.ts";

export type BadgeVariant = "success" | "warning" | "danger" | "info" | "neutral";

export function getBadgeVariant(val: string, colName?: string): BadgeVariant | null {
  if (!val || val === "—") return null;
  const s = val.toLowerCase().replace(/[_\s-]+/g, "");

  // High / Critical / Danger / Cancelled / Blocked / Overdue
  if (["cancelled", "canceled", "blocked", "failed", "rejected", "overdue", "urgent", "critical", "high"].includes(s)) {
    return "danger";
  }
  // Success / Completed / Active / Paid / Approved / Published / Done / Low
  if (["completed", "done", "active", "paid", "approved", "published", "resolved", "success", "low"].includes(s)) {
    return "success";
  }
  // Warning / In Progress / Pending / Review / Medium
  if (["inprogress", "pending", "review", "waiting", "medium", "paused", "draft"].includes(s)) {
    return "warning";
  }
  // Info / Open / New / Todo
  if (["open", "new", "todo", "scheduled", "lead", "info"].includes(s)) {
    return "info";
  }
  // Check if column itself is status / priority / state / stage
  if (colName && ["status", "priority", "state", "stage"].includes(colName.toLowerCase())) {
    return "info";
  }
  return null;
}

export function renderCellContent(val: string, col: string) {
  const variant = getBadgeVariant(val, col);
  if (variant) {
    return <span className={`blk-pill blk-pill-${variant}`}>{val}</span>;
  }
  return val;
}

export function DataTable({ block, rows, state, error, onAction }: BlockHostProps<{ entity: string; columns?: string[]; create?: boolean; row_link?: string }>) {
  const st = resolveState(rows, undefined, state, error);
  const cols = (block.props.columns && block.props.columns.length > 0)
    ? block.props.columns
    : (rows && rows.length > 0 ? Object.keys(rows[0]).filter(k => k !== "id") : []);
  
  const [search, setSearch] = React.useState("");
  const [sortCol, setSortCol] = React.useState<string | null>(null);
  const [sortAsc, setSortAsc] = React.useState<boolean>(true);
  const importRef = React.useRef<HTMLInputElement>(null);

  const q = search.trim().toLowerCase();
  const filteredRows = React.useMemo(() => {
    let list = rows ?? [];
    if (q) {
      list = list.filter((r) =>
        cols.some((c) => displayPath(r, c).toLowerCase().includes(q))
      );
    }
    if (sortCol) {
      list = [...list].sort((a, b) => {
        const valA = displayPath(a, sortCol);
        const valB = displayPath(b, sortCol);
        const numA = Number(valA);
        const numB = Number(valB);
        let cmp = 0;
        if (!isNaN(numA) && !isNaN(numB)) {
          cmp = numA - numB;
        } else {
          cmp = valA.localeCompare(valB, undefined, { numeric: true, sensitivity: "base" });
        }
        return sortAsc ? cmp : -cmp;
      });
    }
    return list;
  }, [rows, q, sortCol, sortAsc, cols]);

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
          <div className="blk-table-toolbar">
            <div className="blk-search-box">
              <svg className="blk-search-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8"></circle>
                <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
              </svg>
              <input
                type="text"
                className="blk-search-input"
                placeholder={`Search ${cols.length ? cols.slice(0, 3).join(", ") : "records"}…`}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                aria-label="Search records"
              />
              {search && (
                <button className="blk-search-clear" onClick={() => setSearch("")} title="Clear search">×</button>
              )}
            </div>
            <div className="blk-table-meta">
              {q ? (
                <span>{filteredRows.length} of {rows?.length ?? 0}</span>
              ) : (
                <span>{rows?.length ?? 0} records</span>
              )}
            </div>
            {actions}
          </div>
          <div className="blk-table-wrap">
            <table className="blk-table">
              <thead>
                <tr>
                  {cols.map((c) => {
                    const isSorted = sortCol === c;
                    return (
                      <th
                        key={c}
                        className="blk-th-sortable"
                        onClick={() => {
                          if (sortCol === c) {
                            setSortAsc(!sortAsc);
                          } else {
                            setSortCol(c);
                            setSortAsc(true);
                          }
                        }}
                        title={`Sort by ${c}`}
                      >
                        <span className="blk-th-content">
                          {c}
                          <span className={`blk-sort-icon ${isSorted ? "active" : ""}`}>
                            {isSorted ? (sortAsc ? "↑" : "↓") : "↕"}
                          </span>
                        </span>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {filteredRows.length === 0 && (rows?.length ?? 0) > 0 ? (
                  <tr>
                    <td colSpan={cols.length} className="blk-no-results">
                      No records matching "{search}"
                    </td>
                  </tr>
                ) : (
                  filteredRows.map((r, i) => (
                    <tr key={String(r["id"] ?? i)}
                      className={block.props.row_link ? "blk-row-link" : undefined}
                      onClick={block.props.row_link ? () => onAction?.("open", r["id"]) : undefined}>
                      {cols.map((c) => <td key={c}>{renderCellContent(displayPath(r, c), c)}</td>)}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      ) : undefined}
    </BlockShell>
  );
}

export function Kanban({ block, rows, state, error, onAction }: BlockHostProps<{
  entity: string; group_by: string; card?: { title?: string; subtitle?: string; badges?: string[] }; drag_transitions?: boolean;
}>) {
  const st = resolveState(rows, undefined, state, error);
  const groupBy = block.props.group_by || "status";
  const groups = new Map<string, Rec[]>();
  for (const r of rows ?? []) {
    const k = String(r[groupBy] ?? "—");
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k)!.push(r);
  }
  const card = block.props.card ?? {};
  const badges = Array.isArray(card.badges) ? card.badges : (typeof card.badges === "string" ? [card.badges] : []);
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
                  {badges.map((b) => {
                    const v = displayPath(r, b);
                    const variant = getBadgeVariant(v, b);
                    return (
                      <em key={b} className={variant ? `blk-pill-${variant}` : undefined}>
                        {v}
                      </em>
                    );
                  })}
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
  const searchCols = Array.isArray(block.props.search)
    ? block.props.search
    : (typeof block.props.search === "string" ? [block.props.search] : []);
  const fieldsCols = Array.isArray(block.props.fields)
    ? block.props.fields
    : (typeof block.props.fields === "string" ? [block.props.fields] : []);
  return (
    <BlockShell state={st} error={error}>
      {st === "ready" ? (
        <div className="blk-filter">
          <input aria-label="search" value={q}
            placeholder={searchCols.length ? `Search ${searchCols.join(", ")}` : "Search…"}
            onChange={(e) => { setQ(e.target.value); onAction?.("search", e.target.value); }} />
          {fieldsCols.map((f) => (
            <input key={f} aria-label={f} placeholder={f}
              onChange={(e) => onAction?.("filter", { [f]: e.target.value })} />
          ))}
        </div>
      ) : undefined}
    </BlockShell>
  );
}
