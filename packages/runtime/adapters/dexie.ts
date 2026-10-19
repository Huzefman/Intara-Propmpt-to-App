/**
 * Dexie adapter (Phase 6, P6.2): persisted client storage. Same
 * StorageAdapter contract as MemoryAdapter — the shared contract suite
 * runs against both (dexie via fake-indexeddb in node, real IndexedDB in
 * the browser). One `records` table per guide ADR-2 (option A): schema
 * changes are metadata edits, no DDL per app.
 *
 * Sync strategy: per-entity pull (syncIn) → delegate to an in-memory
 * engine for query semantics → push (syncOut). Transactions snapshot the
 * table and restore on throw (single-user preview semantics).
 *
 * All operations run through an internal queue: every syncIn clears and
 * reloads the shared in-memory mirror, so two concurrent ops (StrictMode's
 * double effect, automations, parallel lists) would interleave, lose
 * in-flight writes, and add duplicate rows for the same rid. The queue is
 * reentrant so transaction() callbacks can keep calling this adapter.
 */
import { Dexie } from "dexie";
import type { Page, Query, Rec, StorageAdapter } from "./types.ts";
import { MemoryAdapter } from "./memory.ts";

interface Stored { key?: number; entity: string; rid: string; data: Rec; version: number; deleted: number }

function keyOf(id: string | number): string { return String(id); }

/** Is `a` the better surviving row for its (entity, rid) than `b`? Prefer
 * live over tombstoned, then the newest version, then the newest write. */
function betterRow(a: Stored, b: Stored): boolean {
  if (a.deleted !== b.deleted) return a.deleted !== 1;
  if (a.version !== b.version) return a.version > b.version;
  return (a.key ?? 0) > (b.key ?? 0);
}

export class DexieAdapter implements StorageAdapter {
  private db: Dexie;
  private mem = new MemoryAdapter();
  private q: Promise<unknown> = Promise.resolve();
  private inTransaction = false;

  constructor(dbName = "intara") {
    const db = new Dexie(dbName);
    db.version(1).stores({ records: "++key, entity, [entity+rid]" });
    this.db = db;
  }

  private table() { return this.db.table<Stored, number>("records"); }

  /** Serialize an operation behind all previously scheduled ones. Only calls
   * made from inside a transaction() callback bypass the queue (they must,
   * or they would deadlock on their own slot) — everything else, including
   * calls that arrive while another op is mid-flight, waits its turn. */
  private enqueue<T>(fn: () => Promise<T>): Promise<T> {
    if (this.inTransaction) return fn();
    const run = () => fn();
    const p = this.q.then(run, run);
    this.q = p.then(() => undefined, () => undefined);
    return p;
  }

  private async syncIn(entity: string): Promise<void> {
    const rows = await this.table().where("entity").equals(entity).toArray();
    // Earlier builds could persist duplicate rows per (entity, rid) (a
    // seeding race wrote twins); reads must always take the live newest one,
    // never whichever twin happens to load last.
    const best = new Map<string, Stored>();
    for (const r of rows) {
      const cur = best.get(r.rid);
      if (!cur || betterRow(r, cur)) best.set(r.rid, r);
    }
    this.mem.load(entity, [...best.values()].map((r) => ({ data: r.data, version: r.version, deleted: r.deleted === 1 })));
  }

  private async syncOut(entity: string): Promise<void> {
    const t = this.table();
    for (const r of this.mem.snapshot(entity)) {
      const rid = keyOf(r.id);
      const patch = { data: r.data, version: r.version, deleted: r.deleted ? 1 : 0 };
      const dups = await t.where("[entity+rid]").equals([entity, rid]).toArray();
      if (dups.length) {
        await t.update(dups[0].key!, patch);
        for (const d of dups.slice(1)) await t.delete(d.key!); // drop legacy twins
      } else {
        await t.add({ entity, rid, ...patch });
      }
    }
  }

  async list(entity: string, q: Query = {}): Promise<Page<Rec>> {
    return this.enqueue(async () => {
      await this.syncIn(entity);
      return this.mem.list(entity, q);
    });
  }

  async get(entity: string, id: string | number): Promise<Rec | null> {
    return this.enqueue(async () => {
      await this.syncIn(entity);
      return this.mem.get(entity, id);
    });
  }

  async put(entity: string, rec: Rec, expectedVersion?: number): Promise<Rec> {
    return this.enqueue(async () => {
      await this.syncIn(entity);
      try {
        const out = await this.mem.put(entity, rec, expectedVersion);
        await this.syncOut(entity);
        return out;
      } catch (e) {
        await this.syncIn(entity); // drop optimistic state on conflict
        throw e;
      }
    });
  }

  async remove(entity: string, id: string | number): Promise<void> {
    return this.enqueue(async () => {
      await this.syncIn(entity);
      await this.mem.remove(entity, id);
      await this.syncOut(entity);
    });
  }

  async transaction<T>(fn: (tx: StorageAdapter) => Promise<T>): Promise<T> {
    return this.enqueue(async () => {
      const t = this.table();
      const snap = await t.toArray();
      this.inTransaction = true;
      try {
        return await fn(this);
      } catch (e) {
        await t.clear();
        await t.bulkAdd(snap.map(({ key: _k, ...rest }) => rest));
        for (const ent of this.mem.entities()) await this.syncIn(ent);
        throw e;
      } finally {
        this.inTransaction = false;
      }
    });
  }
}
