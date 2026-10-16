/**
 * Client-side automations executor (Phase 8, P8.2): declarative trigger
 * matching + step executors. Runs now (preview), Edge Function later.
 * Unsupported actions (send_email/webhook without providers) are recorded
 * as pending effects — explicit, never silent.
 */
import { evaluate } from "../../spec/formula/formula.ts";
import { toCsv } from "../blocks/csv.ts";
import type { AppSpec, Automation } from "../../spec/app-spec.ts";
import type { Rec, StorageAdapter } from "../adapters/types.ts";

export interface RunEvent {
  type: "record.created" | "record.updated" | "lifecycle.transition" | "schedule" | "manual_button";
  entity?: string;
  record?: Rec;
  prev?: Rec;
  transition?: string;
  button?: string;
}

export interface Effect {
  kind: "set_field" | "create_record" | "notify" | "export_csv" | "deferred";
  detail: string;
  record?: Rec;
}

export interface UserCtx { name?: string; [k: string]: unknown }

function matchTrigger(auto: Automation, ev: RunEvent): boolean {
  const t = auto.trigger;
  if (t.type !== ev.type) return false;
  if (t.entity && t.entity !== ev.entity) return false;
  if (t.type === "lifecycle.transition" && t.transition && t.transition !== ev.transition) return false;
  return true;
}

function coerceValue(value: unknown, record: Rec): unknown {
  // Zero-arg date functions evaluate against now; everything else (including
  // unknown calls) stays literal — never guess, never throw.
  if (typeof value === "string" && /^(today|tomorrow|now|startOfMonth)\(\s*\)$/.test(value.trim())) {
    try {
      return evaluate(`${value.trim()}`, record as Record<string, never>, {});
    } catch {
      return value;
    }
  }
  return value;
}

function whenPasses(when: string | undefined, record: Rec): boolean {
  if (!when) return true;
  try {
    return evaluate(when, record as Record<string, never>, {}) === true;
  } catch {
    return false; // unparsable guard fails closed (step skipped)
  }
}

export async function runAutomations(
  spec: AppSpec,
  db: StorageAdapter,
  ev: RunEvent,
  user: UserCtx = {},
): Promise<Effect[]> {
  const effects: Effect[] = [];
  void user;
  for (const auto of spec.automations ?? []) {
    if (!matchTrigger(auto, ev)) continue;
    const entity = auto.trigger.entity;
    const record = ev.record ?? {};
    for (const step of auto.steps ?? []) {
      if (!whenPasses(step.when, record)) continue;
      const params = step.params ?? {};
      switch (step.action) {
        case "set_field": {
          if (!entity) break;
          const field = (params as Record<string, unknown>)["field"];
          const value = (params as Record<string, unknown>)["value"];
          if (typeof field !== "string" || record["id"] === undefined) break;
          const current = await db.get(entity, record["id"] as string | number);
          if (!current) break;
          await db.put(entity, { ...current, [field]: coerceValue(value, current) });
          effects.push({ kind: "set_field", detail: `${entity}.${String(field)} := ${JSON.stringify(value)}` });
          break;
        }
        case "create_record": {
          const target = (params as Record<string, unknown>)["entity"];
          const values = (params as Record<string, unknown>)["values"];
          if (typeof target !== "string" || typeof values !== "object" || values === null) break;
          const saved = await db.put(target, { ...(values as Rec) });
          effects.push({ kind: "create_record", detail: `${target}/${String(saved["id"])}`, record: saved });
          break;
        }
        case "notify": {
          effects.push({ kind: "notify", detail: String((params as Record<string, unknown>)["message"] ?? auto.id) });
          break;
        }
        case "export_csv": {
          if (!entity) break;
          const { rows } = await db.list(entity, {});
          effects.push({ kind: "export_csv", detail: `${entity}.csv (${rows.length} rows)`, record: { csv: toCsv(rows) } });
          break;
        }
        default:
          // send_email / webhook need providers: recorded, not executed.
          effects.push({ kind: "deferred", detail: `${step.action} requires a provider (not configured)` });
          break;
      }
    }
  }
  return effects;
}
