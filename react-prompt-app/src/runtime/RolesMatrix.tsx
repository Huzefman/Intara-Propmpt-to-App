/**
 * Roles matrix viewer (Phase 8, slice 4): read-only "who can do what" from
 * the spec's access rules via engine.can — the current role's column is
 * highlighted. Editing roles is a spec change (chat-patch/versions), not a
 * preview concern.
 */
import React from "react";
import type { AppSpec } from "../../../packages/spec/app-spec.ts";
import { can } from "../../../packages/runtime/engine/permissions.ts";

const OPS = ["read", "create", "update", "delete"];

export function RolesMatrix({ spec, current }: { spec: AppSpec; current: string }) {
  const entities = spec.model.entities.map((e) => e.id);
  const roles = spec.access.roles.map((r) => r.id);
  if (!roles.length || !entities.length) return null;
  return (
    <details className="blk" style={{ marginBottom: 8 }}>
      <summary style={{ cursor: "pointer", fontSize: 12, fontWeight: 600 }}>
        Access · {roles.length} roles × {entities.length} entities
      </summary>
      <table className="blk-table" style={{ marginTop: 8 }}>
        <thead>
          <tr>
            <th>entity</th>
            {roles.map((r) => (
              <th key={r} style={r === current ? { textDecoration: "underline" } : undefined}>{r}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {entities.map((e) => (
            <tr key={e}>
              <td>{e}</td>
              {roles.map((r) => (
                <td key={r} style={r === current ? { fontWeight: 700 } : undefined}>
                  {OPS.filter((op) => can(spec, r, op, e)).join(" ").replace(/read create update delete/, "full") || "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
