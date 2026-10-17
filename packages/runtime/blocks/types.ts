/**
 * Block contract (Phase 6, P6.4): every block renders four states —
 * loading / error / empty / ready — from the same props. Hosts pass rows
 * (entity blocks), record (record blocks) or nothing (static blocks).
 * Pure logic only (node-safe); BlockShell lives in chrome.tsx.
 */

export type Rec = Record<string, unknown>;
export type BlockState = "loading" | "error" | "empty" | "ready";

export interface BlockHostProps<P = Record<string, unknown>> {
  block: { id: string; type: string; props: P };
  rows?: Rec[];
  record?: Rec | null;
  state?: BlockState;
  error?: string;
  onAction?: (action: string, payload?: unknown) => void;
}

export function resolveState(rows?: Rec[], record?: Rec | null, explicit?: BlockState, error?: string): BlockState {
  if (explicit) return explicit;
  if (error) return "error";
  if (rows === undefined && record === undefined) return "loading";
  if (record === null) return "empty";
  if (rows !== undefined && rows.length === 0) return "empty";
  return "ready";
}

/** Human label for hydrated ref values (objects/arrays of rows). */
function labelOf(v: unknown): string {
  if (typeof v !== "object" || v === null) return String(v);
  const o = v as Rec;
  for (const k of ["name", "full_name", "common_name", "title", "label", "id"]) {
    const s = o[k];
    if (typeof s === "string" && s) return s;
  }
  return "—";
}

/** Dotted display paths: customer.name. Missing → em dash. */
export function displayPath(row: Rec, path: string): string {
  let cur: unknown = row;
  for (const seg of path.split(".")) {
    if (typeof cur !== "object" || cur === null) return "—";
    cur = (cur as Rec)[seg];
  }
  if (cur === undefined || cur === null) return "—";
  if (typeof cur === "boolean") return cur ? "yes" : "no";
  if (Array.isArray(cur)) return cur.map(labelOf).join(", ");
  if (typeof cur === "object") return labelOf(cur);
  return String(cur);
}
