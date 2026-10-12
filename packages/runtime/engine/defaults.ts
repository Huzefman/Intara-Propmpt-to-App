/**
 * Defaults (Phase 6, P6.1): fill missing fields from the spec.
 * The special default "now()" stamps the current time (or the fixed `now`
 * passed in — tests stay deterministic): full ISO for datetime, date part
 * for date, time part for time.
 */
import type { Entity } from "../../spec/app-spec.ts";
import type { Rec } from "./errors.ts";

function nowParts(now?: string): { date: string; time: string; datetime: string } {
  const d = now ?? new Date().toISOString();
  return {
    datetime: d,
    date: d.slice(0, 10),
    time: d.slice(11, 19),
  };
}

export function applyDefaults(entity: Entity, partial: Rec, now?: string): Rec {
  const out: Rec = { ...partial };
  const parts = nowParts(now);
  for (const f of entity.fields) {
    if (out[f.id] !== undefined && out[f.id] !== null) continue;
    const d = f.default;
    if (d === undefined) continue;
    if (d === "now()" && (f.type === "date" || f.type === "time" || f.type === "datetime")) {
      out[f.id] = f.type === "date" ? parts.date : f.type === "time" ? parts.time : parts.datetime;
    } else {
      out[f.id] = d;
    }
  }
  return out;
}
