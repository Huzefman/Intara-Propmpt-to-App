/** Shared conformance runner: packages/spec/formula/formula-cases.json through formula.ts. */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { evaluate, FormulaSyntaxError, FormulaError } from "./formula.ts";

const dir = dirname(fileURLToPath(import.meta.url));
const cases: Array<Record<string, unknown>> = JSON.parse(
  readFileSync(join(dir, "formula-cases.json"), "utf8"),
).cases;

function norm(v: unknown): unknown {
  // JSON round-trip normalizes -0 / int-vs-float so TS↔Py comparison is exact.
  return JSON.parse(JSON.stringify(v === undefined ? null : v));
}

test("formula conformance (shared cases)", async (t) => {
  for (const c of cases) {
    await t.test(c.id as string, () => {
      const formula = c.formula as string;
      const record = (c.record ?? {}) as Record<string, never>;
      const related = (c.related ?? {}) as Record<string, never>;
      const ctx = c.now ? { now: c.now as string } : {};
      const wantErr = c.expect_error as string | undefined;
      try {
        const got = norm(evaluate(formula, record, related, ctx));
        if (wantErr) assert.fail(`expected ${wantErr} error, got ${JSON.stringify(got)}`);
        assert.deepEqual(got, norm(c.expect));
      } catch (e) {
        if (!wantErr) throw e;
        const isSyntax = e instanceof FormulaSyntaxError;
        const isEval = e instanceof FormulaError && !(e instanceof FormulaSyntaxError);
        assert.ok(
          (wantErr === "syntax" && isSyntax) || (wantErr === "eval" && isEval),
          `case ${c.id}: wanted ${wantErr}, got ${e instanceof Error ? e.name + ": " + e.message : e}`,
        );
      }
    });
  }
});

test("no eval/Function_no-new-Function", () => {
  const src = readFileSync(join(dir, "formula.ts"), "utf8");
  assert.ok(!/\beval\s*\(/.test(src), "eval( forbidden");
  assert.ok(!/\bFunction\s*\(/.test(src), "Function( forbidden");
});
