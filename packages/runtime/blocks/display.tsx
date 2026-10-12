/** Display blocks: bar chart, month calendar, activity timeline, files, hero. */
import React from "react";
import { BlockShell } from "./chrome.tsx";
import { displayPath, resolveState } from "./types.ts";
import type { BlockHostProps, Rec } from "./types.ts";

export function ChartBar({ block, rows, state, error }: BlockHostProps<{
  entity: string; label_field?: string; value_field?: string;
}>) {
  const st = resolveState(rows, undefined, state, error);
  const lf = block.props.label_field ?? "name";
  const vf = block.props.value_field ?? "value";
  const max = Math.max(1, ...(rows ?? []).map((r) => typeof r[vf] === "number" ? (r[vf] as number) : 0));
  return (
    <BlockShell state={st} error={error}>
      {st === "ready" ? (
        <div className="blk-chart">
          {(rows ?? []).map((r, i) => {
            const v = typeof r[vf] === "number" ? (r[vf] as number) : 0;
            return (
              <div key={String(r["id"] ?? i)} className="blk-row">
                <span>{displayPath(r, lf)}</span>
                <div className="blk-bar"><div style={{ width: `${Math.round((v / max) * 100)}%` }} /></div>
                <em>{v}</em>
              </div>
            );
          })}
        </div>
      ) : undefined}
    </BlockShell>
  );
}

export function CalendarMonth({ block, rows, state, error, onAction }: BlockHostProps<{
  entity: string; date_field?: string; title_field?: string;
}>) {
  const st = resolveState(rows, undefined, state, error);
  const df = block.props.date_field ?? "date";
  const tf = block.props.title_field ?? "name";
  const days = new Map<string, Rec[]>();
  for (const r of rows ?? []) {
    const day = String(r[df] ?? "").slice(0, 10);
    if (!day) continue;
    if (!days.has(day)) days.set(day, []);
    days.get(day)!.push(r);
  }
  return (
    <BlockShell state={st} error={error}>
      {st === "ready" ? (
        <div className="blk-cal">
          {[...days.entries()].sort().map(([d, rs]) => (
            <div key={d} className="blk-day">
              <strong>{d}</strong>
              {rs.map((r, i) => (
                <button key={String(r["id"] ?? i)} onClick={() => onAction?.("open", r["id"])}>
                  {displayPath(r, tf)}
                </button>
              ))}
            </div>
          ))}
        </div>
      ) : undefined}
    </BlockShell>
  );
}

export function ActivityTimeline({ block, rows, state, error }: BlockHostProps<{
  entity: string; text_field?: string; done_field?: string;
}>) {
  const st = resolveState(rows, undefined, state, error);
  const tf = block.props.text_field ?? "note";
  const df = block.props.done_field ?? "done";
  return (
    <BlockShell state={st} error={error}>
      {st === "ready" ? (
        <ol className="blk-timeline">
          {(rows ?? []).map((r, i) => (
            <li key={String(r["id"] ?? i)} className={r[df] ? "done" : ""}>
              {displayPath(r, tf)}
            </li>
          ))}
        </ol>
      ) : undefined}
    </BlockShell>
  );
}

export function FileList({ block, rows, state, error }: BlockHostProps<{
  entity: string; field?: string;
}>) {
  const st = resolveState(rows, undefined, state, error);
  const field = block.props.field ?? "file";
  return (
    <BlockShell state={st} error={error}>
      {st === "ready" ? (
        <ul className="blk-files">
          {(rows ?? []).map((r, i) => {
            const href = r[field];
            return (
              <li key={String(r["id"] ?? i)}>
                {typeof href === "string" && href
                  ? <a href={href}>{href.split("/").pop()}</a>
                  : <span className="blk-nofile">no file</span>}
              </li>
            );
          })}
        </ul>
      ) : undefined}
    </BlockShell>
  );
}

export function ContentHero({ block, state, error, onAction }: BlockHostProps<{
  title?: string; subtitle?: string; cta?: string;
}>) {
  const st = state ?? "ready";
  return (
    <BlockShell state={st} error={error}>
      {st === "ready" ? (
        <div className="blk-hero">
          <h2>{block.props.title ?? ""}</h2>
          {block.props.subtitle ? <p>{block.props.subtitle}</p> : null}
          {block.props.cta ? <button onClick={() => onAction?.("cta")}>{block.props.cta}</button> : null}
        </div>
      ) : undefined}
    </BlockShell>
  );
}
