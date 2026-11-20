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
export function labelOf(v: unknown): string {
  if (typeof v !== "object" || v === null) return String(v);
  const o = v as Rec;
  for (const k of ["name", "full_name", "common_name", "title", "label"]) {
    const s = o[k];
    if (typeof s === "string" && s) return s;
  }
  // A row without its own label (e.g. a join row like a planting) borrows the
  // labels of its hydrated ref fields: "Raised Bed A · Tomato" beats "planting-1".
  const parts: string[] = [];
  for (const x of Object.values(o)) {
    if (x && typeof x === "object" && !Array.isArray(x)) {
      for (const k of ["name", "full_name", "common_name", "title", "label"]) {
        const t = (x as Rec)[k];
        if (typeof t === "string" && t && !parts.includes(t)) { parts.push(t); break; }
      }
    }
    if (parts.length >= 2) break;
  }
  if (parts.length) return parts.join(" · ");
  const id = o["id"];
  return typeof id === "string" || typeof id === "number" ? String(id) : "—";
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

/** Pure resolution of card title, subtitle, and badges with smart fallbacks. */
export function resolveCardContent(r: Rec, card: any = {}, groupBy: string = "status") {
  const cardFields = Array.isArray(card.fields) ? card.fields : [];

  // 1. Resolve Title
  let titleVal = "";
  const titlePath = card.title || cardFields[0];
  if (titlePath) {
    const rawPath = String(titlePath).replace(/[{}]/g, "");
    const v = displayPath(r, rawPath);
    if (v && v !== "—") titleVal = v;
  }
  if (!titleVal) {
    for (const k of ["title", "name", "full_name", "common_name", "label", "summary", "subject", "device", "task_name", "task", "description"]) {
      const v = r[k];
      if (typeof v === "string" && v.trim()) {
        titleVal = v.trim();
        break;
      }
    }
  }
  if (!titleVal) {
    for (const [k, v] of Object.entries(r)) {
      if (!["id", "created_at", groupBy, "_key"].includes(k) && (typeof v === "string" || typeof v === "number")) {
        const str = String(v).trim();
        if (str && str !== "—") {
          titleVal = str;
          break;
        }
      }
    }
  }
  if (!titleVal) {
    const label = labelOf(r);
    if (label && label !== "—") titleVal = label;
  }
  if (!titleVal) {
    titleVal = r["id"] ? String(r["id"]) : "Card";
  }

  // 2. Resolve Subtitle
  let subtitleVal: string | null = null;
  const subtitlePath = card.subtitle || cardFields[1];
  if (subtitlePath) {
    const rawPath = String(subtitlePath).replace(/[{}]/g, "");
    const v = displayPath(r, rawPath);
    if (v && v !== "—") subtitleVal = v;
  }
  if (!subtitleVal) {
    for (const k of ["subtitle", "email", "customer", "project", "author", "category", "description", "note"]) {
      const v = r[k];
      if (typeof v === "string" && v.trim() && v.trim() !== titleVal) {
        subtitleVal = v.trim();
        break;
      } else if (v && typeof v === "object") {
        const l = labelOf(v);
        if (l && l !== "—" && l !== titleVal) {
          subtitleVal = l;
          break;
        }
      }
    }
  }

  // 3. Resolve Badges
  const badgesList: Array<{ label: string; key: string }> = [];
  const rawBadges = Array.isArray(card.badges)
    ? card.badges
    : typeof card.badges === "string"
    ? [card.badges]
    : cardFields.slice(2);

  if (rawBadges.length > 0) {
    for (const b of rawBadges) {
      const rawB = String(b).replace(/[{}]/g, "");
      const v = displayPath(r, rawB);
      if (v && v !== "—") {
        badgesList.push({ label: v, key: rawB });
      }
    }
  } else {
    for (const k of ["priority", "owner", "technician", "role", "tag", "genre", "value", "total", "category", "urgency"]) {
      if (r[k] !== undefined && r[k] !== null && String(r[k]) !== titleVal && String(r[k]) !== subtitleVal) {
        const v = displayPath(r, k);
        if (v && v !== "—") {
          badgesList.push({ label: `${k}: ${v}`, key: k });
          if (badgesList.length >= 2) break;
        }
      }
    }
  }

  return { title: titleVal, subtitle: subtitleVal, badges: badgesList };
}
