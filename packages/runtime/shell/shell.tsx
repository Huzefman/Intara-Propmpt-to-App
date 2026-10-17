/**
 * AppShell (Phase 6, P6.3): thin React shell — nav from navForRole, theme
 * vars on the wrapper, dev RoleSession switcher. Data comes from the
 * adapter-backed hooks the host app wires in; the shell itself holds no
 * fetch logic. Typechecked by tsc; browser tests (Playwright) deferred
 * to browser CI (no browser in this env — see AGENT.md).
 */
import React from "react";
import type { AppSpec } from "../../spec/app-spec.ts";
import { navForRole } from "./nav.ts";
import { themeToCssVars } from "./theme.ts";
import { RoleSession } from "./roles.ts";

export interface ShellProps {
  spec: AppSpec;
  session: RoleSession;
  activePage: string;
  onNavigate: (pageId: string) => void;
  onRole: (role: string) => void;
  children: React.ReactNode;
}

export function AppShell({ spec, session, activePage, onNavigate, onRole, children }: ShellProps) {
  const entries = navForRole(spec, session.current);
  const vars = themeToCssVars(spec.ui.theme) as React.CSSProperties;
  return (
    <div className="app-shell" style={vars}>
      <nav className="app-nav">
        <span className="app-brand">{spec.app.name}</span>
        {entries.map((e) => (
          <button
            key={e.pageId}
            className={e.pageId === activePage ? "active" : ""}
            onClick={() => onNavigate(e.pageId)}
          >
            {e.label}
          </button>
        ))}
        <select
          aria-label="role"
          value={session.current}
          onChange={(ev) => onRole(ev.target.value)}
        >
          {session.roles.map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
      </nav>
      <main className="app-main">{children}</main>
    </div>
  );
}
