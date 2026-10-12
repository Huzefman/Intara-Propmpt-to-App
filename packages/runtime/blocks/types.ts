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

/** Dotted display paths: customer.name. Missing → em dash. */
export function displayPath(row: Rec, path: string): string {
  let cur: unknown = row;
  for (const seg of path.split(".")) {
    if (typeof cur !== "object" || cur === null) return "—";
    cur = (cur as Rec)[seg];
  }
  if (cur === undefined || cur === null) return "—";
  if (typeof cur === "boolean") return cur ? "yes" : "no";
  return String(cur);
}
