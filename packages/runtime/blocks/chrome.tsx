/** Shared block chrome (browser/tsc only): loading/error/empty/ready shell. */
import React from "react";
import type { BlockState } from "./types.ts";

export function BlockShell({ title, state, error, children }: {
  title?: string; state: BlockState; error?: string; children?: React.ReactNode;
}) {
  if (state === "loading") return <div className="blk blk-loading">Loading…</div>;
  if (state === "error") return <div className="blk blk-error" role="alert">{error ?? "Something went wrong"}</div>;
  if (state === "empty") return <div className="blk blk-empty">Nothing here yet</div>;
  return (
    <section className="blk">
      {title ? <h3 className="blk-title">{title}</h3> : null}
      {children}
    </section>
  );
}
