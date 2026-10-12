/**
 * References + onDelete (Phase 6, P6.1).
 * checkRefsExist: every ref/multi_ref value points at a real record.
 * enforceOnDelete: restrict (throw when children exist), cascade (delete
 * them), set_null (nullify their ref). Structural store interface so the
 * engine never imports an adapter (both adapters satisfy it).
 */
import type { AppSpec } from "../../spec/app-spec.ts";
import { EngineError, type Rec } from "./errors.ts";

export interface RefStore {
  list(entity: string, filter?: Record<string, unknown>): Promise<{ rows: Rec[]; total: number }>;
  get(entity: string, id: string | number): Promise<Rec | null>;
  put(entity: string, rec: Rec): Promise<Rec>;
  remove(entity: string, id: string | number): Promise<void>;
}

export interface RefError { field: string; message: string }

function entityOf(spec: AppSpec, entityId: string) {
  return spec.model.entities.find((e) => e.id === entityId);
}

export async function checkRefsExist(
  spec: AppSpec,
  entityId: string,
  record: Rec,
  get: (entity: string, id: string | number) => Promise<Rec | null>,
): Promise<RefError[]> {
  const errors: RefError[] = [];
  const entity = entityOf(spec, entityId);
  if (!entity) return [{ field: "", message: `unknown entity '${entityId}'` }];
  for (const f of entity.fields) {
    if ((f.type !== "ref" && f.type !== "multi_ref") || !f.target) continue;
    if (!entityOf(spec, f.target))
      return [{ field: f.id, message: `ref target '${f.target}' does not exist` }];
    const v = record[f.id];
    if (v === undefined || v === null) continue;
    const ids = f.type === "ref" ? [v] : Array.isArray(v) ? v : [v];
    for (const id of ids) {
      if (typeof id !== "string" && typeof id !== "number") {
        errors.push({ field: f.id, message: "must be a record id" });
        continue;
      }
      if ((await get(f.target, id)) === null)
        errors.push({ field: f.id, message: `'${f.target}/${id}' does not exist` });
    }
  }
  return errors;
}

export async function enforceOnDelete(
  spec: AppSpec,
  store: RefStore,
  entityId: string,
  id: string | number,
): Promise<{ deleted: number; nulled: number }> {
  let deleted = 0;
  let nulled = 0;
  for (const e of spec.model.entities) {
    for (const f of e.fields) {
      if ((f.type !== "ref" && f.type !== "multi_ref") || f.target !== entityId) continue;
      const kids = await store.list(e.id, { [f.id]: id });
      const mode = f.onDelete ?? "restrict";
      if (mode === "restrict" && kids.total > 0)
        throw new EngineError(
          `cannot delete ${entityId}/${id}: ${kids.total} ${e.id} row(s) reference it`);
      if (mode === "cascade") {
        for (const k of kids.rows) {
          const kidId = k["id"];
          if (typeof kidId === "string" || typeof kidId === "number") {
            await store.remove(e.id, kidId);
            deleted++;
          }
        }
      }
      if (mode === "set_null") {
        for (const k of kids.rows) {
          const kidId = k["id"];
          if (typeof kidId !== "string" && typeof kidId !== "number") continue;
          const full = await store.get(e.id, kidId);
          if (full) {
            await store.put(e.id, { ...full, [f.id]: null });
            nulled++;
          }
        }
      }
    }
  }
  return { deleted, nulled };
}
