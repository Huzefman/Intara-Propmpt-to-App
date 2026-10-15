import { test } from "node:test";
import { createClient } from "@supabase/supabase-js";
import { runContract } from "./contract.ts";
import { SupabaseAdapter } from "./supabase.ts";

test("supabase adapter contract (live, opt-in via INTARA_LIVE=1)", async (t) => {
  // Opt-in (not ambient creds): suite stays deterministic under `pytest`;
  // run live explicitly: INTARA_LIVE=1 node --test adapters/supabase.test.ts
  if (process.env["INTARA_LIVE"] !== "1") {
    t.skip("set INTARA_LIVE=1 with SUPABASE_URL/SUPABASE_SERVICE_KEY to run live");
    return;
  }
  const url = process.env["SUPABASE_URL"];
  const key = process.env["SUPABASE_SERVICE_KEY"];
  if (!url || !key) {
    t.skip("SUPABASE_URL/SUPABASE_SERVICE_KEY not set (with INTARA_LIVE=1)");
    return;
  }
  const cfg = { url, key, appId: "" };
  // Scratch app per run (cascade-deleted after): parallel runs never collide.
  const admin = createClient(cfg.url, cfg.key);
  const app = await admin.from("apps").insert({}).select("id").single();
  if (app.error) throw new Error(`scratch app: ${app.error.message}`);
  const appId = app.data.id as string;
  const clean = async () => {
    // hard-delete all rows (contract subtests share entity names)
    await admin.from("records").delete().eq("app_id", appId);
  };
  try {
    await runContract(t, () => new SupabaseAdapter({ ...cfg, appId }), clean);
  } finally {
    await admin.from("apps").delete().eq("id", appId);
  }
});
