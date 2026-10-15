/**
 * Supabase adapter (Phase 8, P8.1): persisted server-side storage over the
 * 007 data-plane `records` table (ADR-2 option A). Same StorageAdapter
 * contract — the shared suite runs against it when credentials exist
 * (SUPABASE_URL + SUPABASE_SERVICE_KEY), skipped otherwise.
 * Sync strategy mirrors DexieAdapter: per-entity pull → in-memory query
 * engine → push. Single-user preview semantics; multi-tenant auth later.
 */
import { createClient } from "@supabase/supabase-js";
import type { SupabaseClient } from "@supabase/supabase-js";
import type { Page, Query, Rec, StorageAdapter } from "./types.ts";
import { MemoryAdapter } from "./memory.ts";

export interface SupabaseConfig { url: string; key: string; appId: string }

export function supabaseEnv(): SupabaseConfig | null {
  const env = (typeof process !== "undefined" ? process.env : {}) as Record<string, string | undefined>;
  const url = env["SUPABASE_URL"];
  const key = env["SUPABASE_SERVICE_KEY"];
  const appId = env["SUPABASE_APP_ID"];
  if (!url || !key || !appId) return null;
  return { url, key, appId };
}

export class SupabaseAdapter implements StorageAdapter {
  private db: SupabaseClient;
  private appId: string;
  private mem = new MemoryAdapter();

  constructor(cfg: SupabaseConfig) {
    this.db = createClient(cfg.url, cfg.key);
    this.appId = cfg.appId;
  }

  private async syncIn(entity: string): Promise<void> {
    const { data, error } = await this.db.from("records").select("data,version")
      .eq("app_id", this.appId).eq("entity", entity).is("deleted_at", null);
    if (error) throw new Error(`supabase list: ${error.message}`);
    this.mem.load(entity, (data ?? []).map((r) => ({ data: r.data as Rec, version: r.version as number })));
  }

  private async syncOut(entity: string): Promise<void> {
    for (const r of this.mem.snapshot(entity)) {
      const rid = String(r.id);
      const { data: existing } = await this.db.from("records").select("id")
        .eq("app_id", this.appId).eq("entity", entity).eq("data->>id", rid).limit(1);
      const row = {
        app_id: this.appId, entity, data: r.data, version: r.version,
        deleted_at: r.deleted ? new Date().toISOString() : null,
      };
      if (existing && existing.length > 0) {
        const { error } = await this.db.from("records").update(row).eq("id", existing[0].id);
        if (error) throw new Error(`supabase update: ${error.message}`);
      } else {
        const { error } = await this.db.from("records").insert(row);
        if (error) throw new Error(`supabase insert: ${error.message}`);
      }
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
      await this.syncIn(entity);
      throw e;
    }
  }

  async remove(entity: string, id: string | number): Promise<void> {
    await this.syncIn(entity);
    await this.mem.remove(entity, id);
    await this.syncOut(entity);
  }

  async transaction<T>(fn: (tx: StorageAdapter) => Promise<T>): Promise<T> {
    const snap = await this.db.from("records")
      .select("entity,data,version,deleted_at").eq("app_id", this.appId);
    if (snap.error) throw new Error(`supabase snapshot: ${snap.error.message}`);
    try {
      return await fn(this);
    } catch (e) {
      await this.db.from("records").delete().eq("app_id", this.appId);
      if (snap.data && snap.data.length > 0) {
        await this.db.from("records").insert(snap.data.map((r) => ({
          app_id: this.appId, entity: r.entity, data: r.data,
          version: r.version, deleted_at: r.deleted_at,
        })));
      }
      for (const ent of this.mem.entities()) await this.syncIn(ent);
      throw e;
    }
  }
}
