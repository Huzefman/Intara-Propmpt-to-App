/** Block registry metadata (Phase 6, P6.4): node-safe (no JSX imports).
 * Component mapping lives in components.ts (browser/tsc only). */
export interface BlockReg { stability: "stable" | "experimental" }

export const BLOCKS: Record<string, BlockReg> = {
  "data.table": { stability: "stable" },
  "data.kanban": { stability: "stable" },
  "filter.bar": { stability: "stable" },
  "metric.stat": { stability: "stable" },
  "metric.gauge": { stability: "experimental" },
  "record.detail": { stability: "stable" },
  "record.related_list": { stability: "stable" },
  "lifecycle.pipeline": { stability: "stable" },
  "form.record": { stability: "stable" },
  "chart.bar": { stability: "stable" },
  "calendar.month": { stability: "stable" },
  "activity.timeline": { stability: "stable" },
  "file.list": { stability: "stable" },
  "content.hero": { stability: "stable" },
};

export const BLOCK_TYPES = Object.keys(BLOCKS);
