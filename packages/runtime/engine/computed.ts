/**
 * Computed fields (Phase 6, P6.1): evaluate each formula in field order so
 * later formulas see earlier results (labour + parts_total pattern).
 * A failing formula yields null plus an error entry — never a throw.
 */
import { evaluate } from "../../spec/formula/formula.ts";
import type { Entity } from "../../spec/app-spec.ts";
import type { Rec } from "./errors.ts";

export interface ComputedError { field: string; message: string }

export function computeRecord(
  entity: Entity,
  record: Rec,
  related: Record<string, unknown> = {},
): { record: Rec; errors: ComputedError[] } {
  const out: Rec = { ...record };
  const errors: ComputedError[] = [];
  for (const f of entity.fields) {
    const formula = f.computed?.formula;
    if (!formula) continue;
    try {
      const v = evaluate(
        formula,
        out as Record<string, never>,
        related as Record<string, never>,
      );
      out[f.id] = v as unknown;
    } catch (e) {
      out[f.id] = null;
      errors.push({ field: f.id, message: e instanceof Error ? e.message : String(e) });
    }
  }
  return { record: out, errors };
}
