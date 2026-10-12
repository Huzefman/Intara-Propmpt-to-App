/**
 * Dev role switcher (Phase 6, P6.3): preview any role's view of the app.
 * Allowed roles = spec roles with ≥1 visible page (mirrors G1 R21).
 */
import type { AppSpec } from "../../spec/app-spec.ts";
import { EngineError } from "../engine/errors.ts";

export class RoleSession {
  readonly roles: string[];
  current: string;

  constructor(spec: AppSpec, initial?: string) {
    const covered = new Set<string>();
    for (const p of spec.ui.pages) {
      const pr = p.roles ?? [];
      if (pr.length === 0) for (const r of spec.access.roles) covered.add(r.id);
      else for (const r of pr) covered.add(r);
    }
    this.roles = spec.access.roles.map((r) => r.id).filter((id) => covered.has(id));
    if (!this.roles.length) throw new EngineError("spec has no role with a page");
    this.current = initial && this.roles.includes(initial) ? initial : this.roles[0];
  }

  switch(role: string): void {
    if (!this.roles.includes(role)) throw new EngineError(`role '${role}' has no view`);
    this.current = role;
  }
}
