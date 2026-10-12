/**
 * Lifecycle (Phase 6, P6.1): reachability already linted by G1; here the
 * runtime gates each transition by current state, role and guard formula.
 * Records are never mutated — transitions return a new record.
 * A guard that fails to evaluate excludes the transition from listings and
 * fails closed in applyTransition (fail-closed, never guess).
 */
import { evaluate } from "../../spec/formula/formula.ts";
import type { AppSpec, Transition } from "../../spec/app-spec.ts";
import { EngineError, type Rec } from "./errors.ts";

export interface TransitionCtx { role?: string }

function lifecycleOf(spec: AppSpec, entityId: string) {
  const entity = spec.model.entities.find((e) => e.id === entityId);
  if (!entity) throw new EngineError(`unknown entity '${entityId}'`);
  const lc = entity.lifecycle;
  if (!lc) throw new EngineError(`entity '${entityId}' has no lifecycle`);
  return { entity, lc };
}

function guardPasses(t: Transition, record: Rec): boolean {
  if (!t.guard) return true;
  try {
    const v = evaluate(t.guard, record as Record<string, never>, {});
    return v === true || (typeof v === "number" && v !== 0) ||
      (typeof v === "string" && v.length > 0);
  } catch {
    return false;
  }
}

export function allowedTransitions(
  spec: AppSpec,
  entityId: string,
  record: Rec,
  ctx: TransitionCtx = {},
): Transition[] {
  const { lc } = lifecycleOf(spec, entityId);
  const cur = record[lc.field];
  return (lc.transitions ?? []).filter((t) => {
    if (t.from !== cur) return false;
    if (ctx.role && (t.roles ?? []).length > 0 && !t.roles!.includes(ctx.role)) return false;
    return guardPasses(t, record);
  });
}

export function applyTransition(
  spec: AppSpec,
  entityId: string,
  record: Rec,
  transitionId: string,
  ctx: TransitionCtx = {},
): Rec {
  const { lc } = lifecycleOf(spec, entityId);
  const t = (lc.transitions ?? []).find((x) => x.id === transitionId);
  if (!t) throw new EngineError(`unknown transition '${transitionId}'`);
  if (t.from !== record[lc.field])
    throw new EngineError(
      `transition '${transitionId}' needs '${t.from}', record is '${String(record[lc.field])}'`);
  if (ctx.role && (t.roles ?? []).length > 0 && !t.roles!.includes(ctx.role))
    throw new EngineError(`role '${ctx.role}' may not run '${transitionId}'`);
  if (t.guard && !guardPasses(t, record))
    throw new EngineError(`guard blocks '${transitionId}'`);
  return { ...record, [lc.field]: t.to };
}
