/**
 * CSV portability (Phase 8, slice 2): import parsing + export building.
 * No dependencies. Values are strings; type coercion happens at validation
 * (engine) time, never here.
 */
import type { Rec } from "./types.ts";

export function toCsv(rows: Rec[]): string {
  if (!rows.length) return "";
  const cols = [...new Set(rows.flatMap((r) => Object.keys(r)))].filter((c) => c !== "id");
  const esc = (v: unknown) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return ["id," + cols.join(","), ...rows.map((r) => [r["id"], ...cols.map((c) => esc(r[c]))].join(","))].join("\n");
}

export function parseCsv(text: string): Rec[] {
  const rows: string[][] = [];
  let cur = "", inQ = false;
  let row: string[] = [];
  const src = text.replace(/^\uFEFF/, "");
  for (let i = 0; i < src.length; i++) {
    const c = src[i];
    if (inQ) {
      if (c === '"') {
        if (src[i + 1] === '"') { cur += '"'; i++; }
        else inQ = false;
      } else cur += c;
    } else if (c === '"') {
      inQ = true;
    } else if (c === ",") {
      row.push(cur); cur = "";
    } else if (c === "\n" || c === "\r") {
      if (c === "\r" && src[i + 1] === "\n") i++;
      row.push(cur); cur = "";
      if (row.some((x) => x.trim() !== "")) rows.push(row);
      row = [];
    } else cur += c;
  }
  row.push(cur);
  if (row.some((x) => x.trim() !== "")) rows.push(row);
  if (!rows.length) return [];
  const header = rows[0].map((h) => h.trim());
  return rows.slice(1).map((r) => {
    const rec: Rec = {};
    header.forEach((h, j) => {
      if (!h) return;
      const v = (r[j] ?? "").trim();
      // A real `id` column (the export format) round-trips as an upsert key;
      // rows without one are left id-less so the adapter mints a fresh,
      // collision-free id (the old `csv-N` scheme overwrote earlier imports).
      if (h === "id") { if (v) rec["id"] = v; return; }
      rec[h] = v;
    });
    return rec;
  });
}
