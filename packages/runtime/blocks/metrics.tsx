/** Metric blocks: stat cards + gauge. `where` reuses the formula language. */
import React from "react";
import { aggValue } from "./stats.ts";
import type { StatItem } from "./stats.ts";
import { BlockShell } from "./chrome.tsx";
import { resolveState } from "./types.ts";
import type { BlockHostProps, Rec } from "./types.ts";

export function MetricStat({ block, rows, state, error }: BlockHostProps<{ entity: string; items?: StatItem[] }>) {
  const st = resolveState(rows, undefined, state, error);
  return (
    <BlockShell state={st} error={error}>
      {st === "ready" ? (
        <div className="blk-stats">
          {(block.props.items ?? []).map((it) => (
            <div key={it.label} className="blk-stat">
              <span>{it.label}</span>
              <strong>{aggValue(rows ?? [], it)}</strong>
            </div>
          ))}
        </div>
      ) : undefined}
    </BlockShell>
  );
}

export function MetricGauge({ block, rows, state, error }: BlockHostProps<{ entity: string; field?: string; max?: number; label?: string }>) {
  const st = resolveState(rows, undefined, state, error);
  const field = block.props.field ?? "value";
  const total = (rows ?? []).reduce((s, r) => s + (typeof r[field] === "number" ? (r[field] as number) : 0), 0);
  const max = block.props.max ?? Math.max(total, 1);
  const pct = Math.min(100, Math.round((total / max) * 100));
  return (
    <BlockShell state={st} error={error}>
      {st === "ready" ? (
        <div className="blk-gauge">
          <span>{block.props.label ?? field}: {total}</span>
          <div className="blk-bar"><div style={{ width: `${pct}%` }} /></div>
        </div>
      ) : undefined}
    </BlockShell>
  );
}
