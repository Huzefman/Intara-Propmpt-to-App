/**
 * Block → component mapping (browser/tsc only — imports .tsx, never loaded
 * in node tests; blocks.test.ts greps this file for completeness).
 */
import type { ReactElement } from "react";
import type { BlockHostProps } from "./types.ts";
import { DataTable, FilterBar, Kanban } from "./data.tsx";
import { MetricGauge, MetricStat } from "./metrics.tsx";
import { FormRecord, LifecyclePipeline, RecordDetail, RelatedList } from "./record.tsx";
import { ActivityTimeline, CalendarMonth, ChartBar, ContentHero, FileList } from "./display.tsx";

export type AnyBlockProps = BlockHostProps<Record<string, unknown>>;
/** Function-component shape (avoids class-variance noise in JSX use). */
export type BlockComponent = (props: AnyBlockProps) => ReactElement | null;

export const BLOCK_COMPONENTS: Record<string, BlockComponent> = {
  "data.table": DataTable as unknown as BlockComponent,
  "data.kanban": Kanban as unknown as BlockComponent,
  "filter.bar": FilterBar as unknown as BlockComponent,
  "metric.stat": MetricStat as unknown as BlockComponent,
  "metric.gauge": MetricGauge as unknown as BlockComponent,
  "record.detail": RecordDetail as unknown as BlockComponent,
  "record.related_list": RelatedList as unknown as BlockComponent,
  "lifecycle.pipeline": LifecyclePipeline as unknown as BlockComponent,
  "form.record": FormRecord as unknown as BlockComponent,
  "chart.bar": ChartBar as unknown as BlockComponent,
  "calendar.month": CalendarMonth as unknown as BlockComponent,
  "activity.timeline": ActivityTimeline as unknown as BlockComponent,
  "file.list": FileList as unknown as BlockComponent,
  "content.hero": ContentHero as unknown as BlockComponent,
};
