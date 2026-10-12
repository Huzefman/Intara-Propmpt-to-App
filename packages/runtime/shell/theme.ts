/** Shell theme (Phase 6, P6.3): spec tokens → CSS custom properties. */
import type { Theme } from "../../spec/app-spec.ts";

const DENSITY: Record<string, string> = { compact: "4px", comfortable: "8px", spacious: "12px" };

export function themeToCssVars(theme?: Theme): Record<string, string> {
  const t = theme ?? {};
  return {
    "--intara-archetype": t.archetype ?? "table-first",
    "--intara-palette": t.palette ?? "slate",
    "--intara-density": t.density ?? "comfortable",
    "--intara-spacing": DENSITY[t.density ?? "comfortable"] ?? DENSITY["comfortable"],
    "--intara-radius": t.radius ?? "md",
    "--intara-fonts": t.fonts ?? "inter",
  };
}
