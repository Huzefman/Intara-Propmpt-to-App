/**
 * G4 — render smoke (Phase 6, P6.5): every block type renders to HTML from
 * its fixture without throwing, and AppShell renders every gold spec.
 * Runs in node via react-dom/server (no browser). Browser interaction
 * (clicks, drags) stays Playwright's job in browser CI.
 */
import { createElement } from "react";
import { renderToString } from "react-dom/server";
import type { AppSpec } from "../../spec/app-spec.ts";
import { RoleSession } from "../shell/roles.ts";

async function components() {
  // Dynamic: .tsx loads via testing/tsx-loader.mjs (node can't strip tsx).
  return import("../blocks/components.ts");
}

async function shell() {
  return import("../shell/shell.tsx");
}

export interface G4Failure { check: string; message: string }
export interface G4Result { checks: number; failures: G4Failure[] }

export async function smokeBlocks(
  fixtures: Record<string, { props: Record<string, unknown>; rows?: Array<Record<string, unknown>>; record?: Record<string, unknown> | null }>,
): Promise<G4Result> {
  const { BLOCK_COMPONENTS } = await components();
  const failures: G4Failure[] = [];
  let checks = 0;
  for (const [type, fx] of Object.entries(fixtures)) {
    const C = BLOCK_COMPONENTS[type];
    checks++;
    if (!C) { failures.push({ check: `block:${type}`, message: "no component" }); continue; }
    try {
      const html = renderToString(
        createElement(C as never, {
          block: { id: "g4", type, props: fx.props },
          rows: fx.rows, record: fx.record,
        } as never));
      checks++;
      if (typeof html !== "string" || html.length < 20)
        failures.push({ check: `block:${type}`, message: "empty render" });
    } catch (e) {
      failures.push({ check: `block:${type}`, message: `threw: ${(e as Error).message}` });
    }
  }
  return { checks, failures };
}

export async function smokeShell(spec: AppSpec, name: string): Promise<G4Result> {
  const { AppShell } = await shell();
  const failures: G4Failure[] = [];
  let checks = 0;
  try {
    const session = new RoleSession(spec);
    checks++;
    const first = spec.ui.pages[0];
    const html = renderToString(
      createElement(AppShell, {
        spec, session, activePage: first.id,
        onNavigate: () => {}, onRole: () => {},
        children: "g4",
      }));
    checks++;
    if (!html.includes(spec.app.name))
      failures.push({ check: `shell:${name}`, message: "app name missing" });
    for (const item of (spec.ui.nav ?? []).slice(0, 3)) {
      checks++;
      if (!html.includes(item.label))
        failures.push({ check: `shell:${name}`, message: `nav label ${item.label} missing` });
    }
  } catch (e) {
    failures.push({ check: `shell:${name}`, message: `threw: ${(e as Error).message}` });
  }
  return { checks, failures };
}
