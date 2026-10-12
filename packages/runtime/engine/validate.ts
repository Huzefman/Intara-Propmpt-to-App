/**
 * Record validation (Phase 6, P6.1): required + per-type checks.
 * Computed fields are outputs, not inputs — skipped here (see computed.ts).
 * Cross-record checks (unique, ref existence) need a store: see refs.ts.
 * Unknown record keys are ignored (forward-compat with newer specs).
 */
import type { Entity, EnumDef, SpecField } from "../../spec/app-spec.ts";
import type { Rec } from "./errors.ts";

export interface FieldError { field: string; message: string }

function isFiniteNumber(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

function checkType(f: SpecField, value: unknown, enums: Record<string, EnumDef>): string | null {
  switch (f.type) {
    case "int":
      return Number.isInteger(value) ? null : "must be an integer";
    case "decimal":
    case "money":
    case "rating":
      return isFiniteNumber(value) ? null : "must be a number";
    case "bool":
      return typeof value === "boolean" ? null : "must be true/false";
    case "text":
    case "longtext":
    case "email":
    case "phone":
    case "url":
    case "date":
    case "datetime":
    case "time":
    case "file":
    case "image":
    case "color":
      return typeof value === "string" ? null : "must be text";
    case "enum": {
      if (typeof value !== "string") return "must be text";
      const def = f.enum ? enums[f.enum] : undefined;
      if (def && !def.values.some((v) => v.value === value))
        return `must be one of ${(def.values.map((v) => v.value)).join(", ")}`;
      return null;
    }
    case "multi_enum":
      return Array.isArray(value) && value.every((x) => typeof x === "string")
        ? null : "must be a list of text";
    case "ref":
      return typeof value === "string" || typeof value === "number"
        ? null : "must be a record id";
    case "multi_ref":
      return Array.isArray(value) ? null : "must be a list of record ids";
    case "json":
      return null;
    default:
      return `unknown field type '${(f as { type: string }).type}'`;
  }
}

export function validateRecord(
  entity: Entity,
  record: Rec,
  enums: Record<string, EnumDef> = {},
): FieldError[] {
  const errors: FieldError[] = [];
  for (const f of entity.fields) {
    if (f.computed) continue;
    const v = record[f.id];
    if (v === undefined || v === null) {
      if (f.required) errors.push({ field: f.id, message: "is required" });
      continue;
    }
    const bad = checkType(f, v, enums);
    if (bad) errors.push({ field: f.id, message: bad });
  }
  return errors;
}
