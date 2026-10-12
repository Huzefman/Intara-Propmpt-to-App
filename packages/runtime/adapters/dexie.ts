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
 */
import { Dexie } from "dexie";
import type { Page, Query, Rec, StorageAdapter } from "./types.ts";
import { MemoryAdapter } from "./memory.ts";

interface Stored { key?: number; entity: string; rid: string; data: Rec; version: number; deleted: number }

function keyOf(id: string | number): string { return String(id); }

export class DexieAdapter implements StorageAdapter {
  private db: Dexie;
  private mem = new MemoryAdapter();

  constructor(dbName = "intara") {
    const db = new Dexie(dbName);
    db.version(1).stores({ records: "++key, entity, [entity+rid]" });
    this.db = db;
  }

  private table() { return this.db.table<Stored, number>("records"); }

  private async syncIn(entity: string): Promise<void> {
    const rows = await this.table().where("entity").equals(entity).toArray();
    this.mem.load(entity, rows.map((r) => ({ data: r.data, version: r.version, deleted: r.deleted === 1 })));
  }

  private async syncOut(entity: string): Promise<void> {
    const t = this.table();
    for (const r of this.mem.snapshot(entity)) {
      const rid = keyOf(r.id);
      const existing = await t.where("[entity+rid]").equals([entity, rid]).first();
      const row: Stored = { entity, rid, data: r.data, version: r.version, deleted: r.deleted ? 1 : 0 };
      if (existing) await t.update(existing.key!, { data: row.data, version: row.version, deleted: row.deleted });
      else await t.add(row);
    }
  }

  async list(entity: string, q: Query = {}): Promise<Page<Rec>> {
    await this.syncIn(entity);
    return this.mem.list(entity, q);
  }

  async get(entity: string, id: string | number): Promise<Rec | null> {
    await this.syncIn(entity);
    return this.mem.get(entity, id);
  }

  async put(entity: string, rec: Rec, expectedVersion?: number): Promise<Rec> {
    await this.syncIn(entity);
    try {
      const out = await this.mem.put(entity, rec, expectedVersion);
      await this.syncOut(entity);
      return out;
    } catch (e) {
      await this.syncIn(entity); // drop optimistic state on conflict
      throw e;
    }
  }

  async remove(entity: string, id: string | number): Promise<void> {
    await this.syncIn(entity);
    await this.mem.remove(entity, id);
    await this.syncOut(entity);
  }

  async transaction<T>(fn: (tx: StorageAdapter) => Promise<T>): Promise<T> {
    const t = this.table();
    const snap = await t.toArray();
    try {
      return await fn(this);
    } catch (e) {
      await t.clear();
      await t.bulkAdd(snap.map(({ key: _k, ...rest }) => rest));
      for (const ent of this.mem.entities()) await this.syncIn(ent);
      throw e;
    }
  }
}
