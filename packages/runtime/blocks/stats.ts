/** Metric aggregation over rows (node-safe; used by metrics.tsx). */
import { evaluate } from "../../spec/formula/formula.ts";
import type { Rec } from "./types.ts";

export interface StatItem { label: string; agg: "count" | "sum" | "avg"; field?: string; where?: string }

export function rowMatches(row: Rec, where?: string): boolean {
  if (!where) return true;
  try {
    const v = evaluate(where, row as Record<string, never>, {});
    return v === true;
  } catch {
    return false; // unparsable filter fails closed (row excluded)
  }
}

export function aggValue(rows: Rec[], item: StatItem): number | string {
  const rs = rows.filter((r) => rowMatches(r, item.where));
  if (item.agg === "count") return rs.length;
  const nums = rs.map((r) => r[item.field ?? ""]).filter((x): x is number => typeof x === "number");
  if (!nums.length) return 0;
  const sum = nums.reduce((s, x) => s + x, 0);
  return item.agg === "sum" ? sum : Math.round((sum / nums.length) * 100) / 100;
}
