/**
 * Memory adapter (Phase 6, P6.2): preview + tests. Optimistic concurrency
 * via per-record version; transaction snapshots and rolls back on throw.
 */
import { VersionConflict } from "./types.ts";
import type { Page, Query, Rec, StorageAdapter } from "./types.ts";

interface Row { id: string | number; data: Rec; version: number; deleted: boolean }

function isOps(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v) &&
    ["eq", "ne", "gt", "gte", "lt", "lte", "in"].some((k) => k in (v as object));
}

function cmpVal(a: unknown, op: string, b: unknown): boolean {
  if (op === "eq") return JSON.stringify(a) === JSON.stringify(b);
  if (op === "ne") return JSON.stringify(a) !== JSON.stringify(b);
  if (op === "in") return Array.isArray(b) && b.some((x) => JSON.stringify(x) === JSON.stringify(a));
  if (typeof a !== "number" && typeof a !== "string") return false;
  if (typeof b !== "number" && typeof b !== "string") return false;
  if (typeof a !== typeof b) return false;
  if (op === "gt") return a > b;
  if (op === "gte") return a >= b;
  if (op === "lt") return a < b;
  if (op === "lte") return a <= b;
  return false;
}

function matches(data: Rec, filter?: Query["filter"]): boolean {
  if (!filter) return true;
  return Object.entries(filter).every(([field, cond]) => {
    if (isOps(cond)) return Object.entries(cond).every(([op, v]) => cmpVal(data[field], op, v));
    return JSON.stringify(data[field]) === JSON.stringify(cond);
  });
}

function cmpRows(a: Rec, b: Rec, field: string, dir: "asc" | "desc"): number {
  const x = a[field], y = b[field];
  let c = 0;
  if (typeof x === "number" && typeof y === "number") c = x - y;
  else c = String(x ?? "").localeCompare(String(y ?? ""));
  return dir === "asc" ? c : -c;
}

let autoId = 1;

/** Id for a row stored without one. Must be unique across sessions: the old
 * `m${autoId}` reset on every page load and silently overwrote a persisted
 * row of the same id (imports/seed collisions). */
function genId(): string {
  const c = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto;
  if (c?.randomUUID) return c.randomUUID();
  return `r${Date.now().toString(36)}-${autoId++}`;
}

export class MemoryAdapter implements StorageAdapter {
  protected tables = new Map<string, Map<string | number, Row>>();

  protected table(entity: string): Map<string | number, Row> {
    let t = this.tables.get(entity);
    if (!t) { t = new Map(); this.tables.set(entity, t); }
    return t;
  }

  protected visible(entity: string): Row[] {
    return [...this.table(entity).values()].filter((r) => !r.deleted);
  }

  /** Entity names currently materialized. */
  entities(): string[] {
    return [...this.tables.keys()];
  }

  /** Full entity state (incl. tombstones) for persistence sync. */  snapshot(entity: string): Array<{ id: string | number; data: Rec; version: number; deleted: boolean }> {
    return [...this.table(entity).values()].map((r) => ({ ...r, data: { ...r.data } }));
  }

  /** Replace entity state wholesale (persistence sync-in). */
  load(entity: string, rows: Array<{ data: Rec; version: number; deleted?: boolean }>): void {
    const t = this.table(entity);
    t.clear();
    for (const r of rows) {
      const id = r.data["id"] as string | number;
      t.set(id, { id, data: { ...r.data }, version: r.version, deleted: !!r.deleted });
    }
  }

  async list(entity: string, q: Query = {}): Promise<Page<Rec>> {
    let rows = this.visible(entity).filter((r) => matches(r.data, q.filter));
    if (q.search && q.search.term) {
      const term = q.search.term.toLowerCase();
      rows = rows.filter((r) => q.search!.fields.some((f) =>
        String(r.data[f] ?? "").toLowerCase().includes(term)));
    }
    for (const s of (q.sort ?? []).slice().reverse())
      rows = rows.slice().sort((a, b) => cmpRows(a.data, b.data, s.field, s.dir));
    const total = rows.length;
    const off = q.offset ?? 0;
    const lim = q.limit ?? total;
    return { rows: rows.slice(off, off + lim).map((r) => ({ ...r.data })), total };
  }

  async get(entity: string, id: string | number): Promise<Rec | null> {
    const r = this.table(entity).get(id);
    return r && !r.deleted ? { ...r.data } : null;
  }

  async put(entity: string, rec: Rec, expectedVersion?: number): Promise<Rec> {
    const t = this.table(entity);
    const id = (rec["id"] ?? genId()) as string | number;
    const prev = t.get(id);
    if (expectedVersion !== undefined) {
      const cur = prev && !prev.deleted ? prev.version : 0;
      if (cur !== expectedVersion)
        throw new VersionConflict(`expected v${expectedVersion}, have v${cur}`);
    }
    const version = (prev && !prev.deleted ? prev.version : 0) + 1;
    const data = { ...rec, id };
    t.set(id, { id, data, version, deleted: false });
    return { ...data };
  }

  async remove(entity: string, id: string | number): Promise<void> {
    const r = this.table(entity).get(id);
    if (r) r.deleted = true; // soft delete
  }

  async transaction<T>(fn: (tx: StorageAdapter) => Promise<T>): Promise<T> {
    const snap = new Map<string, Map<string | number, Row>>();
    for (const [k, v] of this.tables) {
      const inner = new Map<string | number, Row>();
      for (const [ik, iv] of v) inner.set(ik, { ...iv, data: { ...iv.data } });
      snap.set(k, inner);
    }
    try {
      return await fn(this);
    } catch (e) {
      this.tables = snap;
      throw e;
    }
  }
}
