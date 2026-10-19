/**
 * CreateDialog (QA pass 2): the runtime blocks emit `create` from tables
 * ("New") and related lists ("Add"), but the host had no handler — those
 * buttons were dead in every preview. This is the host-level, spec-driven
 * form: every writable spec field, enum selects from the spec's enum
 * definitions, ref pickers from live rows, field defaults applied, and
 * `via` prefills when opened from a related list with a parent selected.
 */
import React from "react";
import type { AppSpec, Entity, SpecField } from "../../../packages/spec/app-spec.ts";
import { displayPath, labelOf } from "../../../packages/runtime/blocks/types.ts";
import type { Rec } from "../../../packages/runtime/blocks/types.ts";

type Rows = Record<string, Array<Record<string, unknown>>>;

function refLabel(r: Rec): string {
  for (const p of ["name", "title", "label", "device", "customer_name"]) {
    const v = displayPath(r, p);
    if (v !== "—") return v;
  }
  const l = labelOf(r);
  return l === "—" ? String(r["id"] ?? "") : l;
}

function fieldLabel(f: SpecField): string {
  return f.id.replace(/_/g, " ");
}

function coerce(f: SpecField, raw: unknown): unknown {
  if (f.type === "bool") return !!raw;
  if (typeof raw !== "string") return raw; // arrays (multi_*) pass through
  if (raw === "") return undefined;
  if (f.type === "int") {
    const n = parseInt(raw, 10);
    return Number.isFinite(n) ? n : raw;
  }
  if (f.type === "decimal" || f.type === "money" || f.type === "rating") {
    const n = parseFloat(raw);
    return Number.isFinite(n) ? n : raw;
  }
  return raw;
}

export function CreateDialog({ spec, entity, rows, defaults, mode = 'create', onCancel, onSubmit }: {
  spec: AppSpec;
  entity: Entity;
  rows: Rows;
  defaults?: Rec;
  mode?: 'create' | 'edit';
  onCancel: () => void;
  onSubmit: (values: Rec) => void;
}) {
  const allFields = entity.fields.filter((f) => !f.computed);
  // The lifecycle field is driven by pipeline transitions, not typed in; its
  // value still travels through `values` (creation default / edit unchanged).
  const fields = allFields.filter((f) => f.id !== entity.lifecycle?.field);
  const initial: Rec = {};
  for (const f of allFields) if (f.default !== null && f.default !== undefined) initial[f.id] = f.default;
  if (entity.lifecycle) initial[entity.lifecycle.field] = entity.lifecycle.initial;
  Object.assign(initial, defaults ?? {});
  const [values, setValues] = React.useState<Rec>(initial);
  const set = (k: string, v: unknown) => setValues((prev) => ({ ...prev, [k]: v }));

  function input(f: SpecField) {
    const val = values[f.id];
    const req = !!f.required;
    if (f.type === "bool") {
      return (
        <input type="checkbox" checked={!!val}
          onChange={(e) => set(f.id, e.target.checked)} />
      );
    }
    if (f.type === "longtext" || f.type === "json") {
      return (
        <textarea value={String(val ?? "")} required={req}
          onChange={(e) => set(f.id, e.target.value)} />
      );
    }
    if (f.type === "enum" || f.type === "multi_enum") {
      const def = spec.model.enums?.find((e) => e.id === f.enum);
      const opts = def?.values ?? [];
      if (f.type === "multi_enum") {
        return (
          <select multiple value={Array.isArray(val) ? (val as string[]) : []} required={req}
            onChange={(e) => set(f.id, Array.from(e.target.selectedOptions, (o) => o.value))}>
            {opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        );
      }
      return (
        <select value={String(val ?? "")} required={req}
          onChange={(e) => set(f.id, e.target.value)}>
          <option value="">—</option>
          {opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      );
    }
    if (f.type === "ref" || f.type === "multi_ref") {
      const opts = rows[f.target ?? ""] ?? [];
      if (f.type === "multi_ref") {
        return (
          <select multiple value={Array.isArray(val) ? (val as string[]) : []} required={req}
            onChange={(e) => set(f.id, Array.from(e.target.selectedOptions, (o) => o.value))}>
            {opts.map((r) => (
              <option key={String(r["id"])} value={String(r["id"])}>{refLabel(r)}</option>
            ))}
          </select>
        );
      }
      return (
        <select value={String(val ?? "")} required={req}
          onChange={(e) => set(f.id, e.target.value)}>
          <option value="">—</option>
          {opts.map((r) => (
            <option key={String(r["id"])} value={String(r["id"])}>{refLabel(r)}</option>
          ))}
        </select>
      );
    }
    const type =
      f.type === "int" || f.type === "decimal" || f.type === "money" || f.type === "rating" ? "number"
        : f.type === "date" ? "date"
          : f.type === "datetime" ? "datetime-local"
            : f.type === "time" ? "time"
              : f.type === "email" ? "email"
                : f.type === "phone" ? "tel"
                  : f.type === "url" || f.type === "file" || f.type === "image" ? "url"
                    : "text";
    return (
      <input type={type} value={String(val ?? "")} required={req}
        onChange={(e) => set(f.id, e.target.value)} />
    );
  }

  return (
    <div className="blk-modal" role="dialog" aria-label={`${mode === 'edit' ? 'Edit' : 'New'} ${entity.label}`}>
      <form className="blk-modal-card blk-form"
        onSubmit={(e) => {
          e.preventDefault();
          const out: Rec = {};
          if (values['id'] !== undefined) out['id'] = values['id'];
          for (const f of allFields) {
            const v = coerce(f, values[f.id]);
            if (v !== undefined) out[f.id] = v;
          }
          onSubmit(out);
        }}>
        <h3>{mode === 'edit' ? `Edit ${entity.label}` : `New ${entity.label}`}</h3>
        {fields.map((f) => (
          <label key={f.id}>
            {fieldLabel(f)}{f.required ? " *" : ""}
            {input(f)}
          </label>
        ))}
        <div className="blk-modal-actions">
          <button type="button" onClick={onCancel}>Cancel</button>
          <button type="submit">{mode === 'edit' ? 'Save' : 'Create'}</button>
        </div>
      </form>
    </div>
  );
}
