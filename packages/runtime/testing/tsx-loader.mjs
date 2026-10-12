/**
 * Node ESM loader: transpile .tsx on the fly for G4 render smoke.
 * Node's type-stripping handles .ts but not .tsx; this uses the repo's
 * TypeScript (react-prompt-app) via transpileModule — no new dependency.
 * Registered by g4.test.ts before any .tsx import; .ts keeps native loading.
 */
import { createRequire } from "node:module";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const req = createRequire(join(here, "..", "..", "..", "react-prompt-app", "package.json"));
const ts = req("typescript");

export async function load(url, context, nextLoad) {
  if (url.endsWith(".tsx")) {
    const source = await readFile(new URL(url), "utf8");
    const out = ts.transpileModule(source, {
      compilerOptions: {
        module: ts.ModuleKind.ESNext,
        target: ts.ScriptTarget.ES2022,
        jsx: ts.JsxEmit.ReactJSX,
      },
    });
    return { format: "module", source: out.outputText, shortCircuit: true };
  }
  return nextLoad(url, context);
}
