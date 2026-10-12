/** Shell routing (Phase 6, P6.3): page table straight from the spec. */
import type { Page } from "../../spec/app-spec.ts";

export interface Route { path: string; pageId: string; title: string }

export function buildRoutes(pages: Page[]): Route[] {
  return pages.map((p) => ({ path: p.route, pageId: p.id, title: p.title }));
}

export function routeForPage(pages: Page[], pageId: string): Route | null {
  const p = pages.find((x) => x.id === pageId);
  return p ? { path: p.route, pageId: p.id, title: p.title } : null;
}
