/** Display blocks: bar chart, month calendar, activity timeline, files, hero. */
import React from "react";
import { BlockShell } from "./chrome.tsx";
import { displayPath, resolveState } from "./types.ts";
import type { BlockHostProps, Rec } from "./types.ts";

const TEXT_PATHS = ["title", "name", "common_name", "note"];

/** First non-empty label among an optional override and common text fields. */
function textOf(r: Rec, override?: string): string {
  for (const p of [override, ...TEXT_PATHS].filter(Boolean) as string[]) {
    const v = displayPath(r, p);
    if (v !== "—") return v;
  }
  return "";
}

export function ChartBar({ block, rows, state, error }: BlockHostProps<{
  entity: string; title?: string; x: string; y?: string;
}>) {
  const st = resolveState(rows, undefined, state, error);
  const lf = block.props.x;
  const ymode = block.props.y ?? "count";
  const groups = new Map<string, number>();
  for (const r of rows ?? []) {
    const label = displayPath(r, lf);
    const v = ymode === "count" ? 1
      : typeof r[ymode] === "number" ? (r[ymode] as number) : 0;
    groups.set(label, (groups.get(label) ?? 0) + v);
  }
  const max = Math.max(1, ...groups.values());
  return (
    <BlockShell title={block.props.title} state={st} error={error}>
      {st === "ready" ? (
        <div className="blk-chart">
          {[...groups.entries()].map(([label, v], i) => (
            <div key={`${label}-${i}`} className="blk-row">
              <span>{label}</span>
              <div className="blk-bar"><div style={{ width: `${Math.round((v / max) * 100)}%` }} /></div>
              <em>{v}</em>
            </div>
          ))}
        </div>
      ) : undefined}
    </BlockShell>
  );
}

export function CalendarMonth({ block, rows, state, error, onAction }: BlockHostProps<{
  entity: string; date_field: string; title?: string; row_link?: string;
}>) {
  const st = resolveState(rows, undefined, state, error);
  const df = block.props.date_field;
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
                  {textOf(r, block.props.title)}
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
  entity: string; date_field: string; title?: string;
}>) {
  const st = resolveState(rows, undefined, state, error);
  return (
    <BlockShell title={block.props.title} state={st} error={error}>
      {st === "ready" ? (
        <ol className="blk-timeline">
          {(rows ?? []).map((r, i) => (
            <li key={String(r["id"] ?? i)}>
              <span className="blk-date">{displayPath(r, block.props.date_field)}</span>
              {" "}{textOf(r)}
            </li>
          ))}
        </ol>
      ) : undefined}
    </BlockShell>
  );
}

export function FileList({ block, rows, state, error, onAction }: BlockHostProps<{
  entity: string; field?: string; upload?: boolean;
}>) {
  const st = resolveState(rows, undefined, state, error);
  const field = block.props.field ?? "file";
  const fileRef = React.useRef<HTMLInputElement>(null);
  return (
    <BlockShell state={st} error={error}>
      {st === "ready" ? (
        <>
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
          {block.props.upload ? (
            <>
              <button onClick={() => fileRef.current?.click()}>Upload</button>
              <input ref={fileRef} type="file" hidden
                onChange={async (e) => {
                  const f = e.target.files?.[0];
                  if (f) onAction?.("upload", { file: f, filename: f.name, field });
                  e.target.value = "";
                }} />
            </>
          ) : undefined}
        </>
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
