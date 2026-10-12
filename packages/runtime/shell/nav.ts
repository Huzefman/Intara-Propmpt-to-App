/**
 * Shell nav (Phase 6, P6.3): nav items visible to a role. An item with empty
 * roles is public; items pointing at missing pages are dropped (G1 flags
 * them, the shell never crashes on them).
 */
import type { AppSpec } from "../../spec/app-spec.ts";

export interface NavEntry { pageId: string; path: string; label: string; icon?: string }

export function navForRole(spec: AppSpec, role: string): NavEntry[] {
  const pages = new Map(spec.ui.pages.map((p) => [p.id, p]));
  const out: NavEntry[] = [];
  for (const n of spec.ui.nav ?? []) {
    const p = pages.get(n.page);
    if (!p) continue;
    const itemRoles = n.roles ?? [];
    const pageRoles = p.roles ?? [];
    const visible =
      (itemRoles.length === 0 || itemRoles.includes(role)) &&
      (pageRoles.length === 0 || pageRoles.includes(role));
    if (visible) out.push({ pageId: p.id, path: p.route, label: n.label, icon: n.icon });
  }
  return out;
}
