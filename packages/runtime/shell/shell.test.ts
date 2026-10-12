/** Shell core tests (Phase 6, P6.3): routes, nav, theme, role session. */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { AppSpec } from "../../spec/app-spec.ts";
import { buildRoutes, routeForPage } from "./routes.ts";
import { navForRole } from "./nav.ts";
import { themeToCssVars } from "./theme.ts";
import { RoleSession } from "./roles.ts";
import { EngineError } from "../engine/errors.ts";

const dir = dirname(fileURLToPath(import.meta.url));
const repair = JSON.parse(readFileSync(join(dir, "../../spec/exemplars/repair-tracker.json"), "utf8")) as AppSpec;

test("routes come straight from pages", () => {
  const routes = buildRoutes(repair.ui.pages);
  assert.equal(routes.length, 4);
  assert.deepEqual(routeForPage(repair.ui.pages, "jobs"), { path: "/jobs", pageId: "jobs", title: "All jobs" });
  assert.equal(routeForPage(repair.ui.pages, "nope"), null);
});

test("nav filters by role, drops missing pages", () => {
  assert.deepEqual(navForRole(repair, "owner").map((n) => n.pageId), ["board", "jobs", "customers"]);
  assert.deepEqual(navForRole(repair, "technician").map((n) => n.pageId), ["board", "jobs"]);
  const broken = JSON.parse(JSON.stringify(repair)) as AppSpec;
  broken.ui.nav = [...broken.ui.nav, { page: "ghost", label: "Ghost" }];
  assert.equal(navForRole(broken, "owner").length, 3);
});

test("theme tokens map with defaults", () => {
  const vars = themeToCssVars(repair.ui.theme);
  assert.equal(vars["--intara-palette"], "teal");
  assert.equal(vars["--intara-spacing"], "4px");
  const bare = themeToCssVars(undefined);
  assert.equal(bare["--intara-palette"], "slate");
  assert.equal(bare["--intara-spacing"], "8px");
});

test("role session allows covered roles only", () => {
  const s = new RoleSession(repair);
  assert.deepEqual(s.roles, ["owner", "technician"]);
  assert.equal(s.current, "owner");
  s.switch("technician");
  assert.equal(s.current, "technician");
  assert.throws(() => s.switch("ghost"), EngineError);
  assert.equal(new RoleSession(repair, "ghost").current, "owner", "bad initial falls back");
  assert.throws(() => new RoleSession({ ...repair, access: { roles: [], rules: [] } }), EngineError);
});
