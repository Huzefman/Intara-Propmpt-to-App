/**
 * G3 + G4 over all gold specs (Phase 6, P6.5): generated checks per spec,
 * render smoke per block + shell. Zero LLM calls throughout.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { AppSpec } from "../../spec/app-spec.ts";
import { runG3 } from "./g3.ts";

const dir = dirname(fileURLToPath(import.meta.url));
const goldDir = join(dir, "../../spec/exemplars");
const golds = readdirSync(goldDir).filter((f) => f.endsWith(".json")).sort();

test("G3 passes on all gold specs", async (t) => {
  assert.ok(golds.length >= 5, `want 5 golds, have ${golds.length}`);
  for (const file of golds) {
    const spec = JSON.parse(readFileSync(join(goldDir, file), "utf8")) as AppSpec;
    await t.test(file, async () => {
      const res = await runG3(spec, file);
      assert.deepEqual(res.failures, [], `${file}: ${JSON.stringify(res.failures.slice(0, 3))}`);
      assert.ok(res.checks >= 10, `${file}: only ${res.checks} checks`);
    });
  }
});
