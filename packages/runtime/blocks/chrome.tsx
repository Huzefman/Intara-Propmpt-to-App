/** Shared block chrome (browser/tsc only): loading/error/empty/ready shell. */
import React from "react";
import type { BlockState } from "./types.ts";

export function BlockShell({ title, state, error, emptyActions, children }: {
  title?: string; state: BlockState; error?: string; children?: React.ReactNode;
  /** Rendered under the empty message (e.g. a create button, so an empty
   * list can still receive its first record). */
  emptyActions?: React.ReactNode;
}) {
  if (state === "loading") return <div className="blk blk-loading">Loading…</div>;
  if (state === "error") return <div className="blk blk-error" role="alert">{error ?? "Something went wrong"}</div>;
  if (state === "empty") {
    if (!emptyActions) return <div className="blk blk-empty">Nothing here yet</div>;
    return (
      <section className="blk">
        <div className="blk-empty">Nothing here yet</div>
        {emptyActions}
      </section>
    );
  }
  return (
    <section className="blk">
      {title ? <h3 className="blk-title">{title}</h3> : null}
      {children}
    </section>
  );
}
