/**
 * Block → component mapping (browser/tsc only — imports .tsx, never loaded
 * in node tests; blocks.test.ts greps this file for completeness).
 */
import type { ComponentType } from "react";
import type { BlockHostProps } from "./types.ts";
import { DataTable, FilterBar, Kanban } from "./data.tsx";
import { MetricGauge, MetricStat } from "./metrics.tsx";
import { FormRecord, LifecyclePipeline, RecordDetail, RelatedList } from "./record.tsx";
import { ActivityTimeline, CalendarMonth, ChartBar, ContentHero, FileList } from "./display.tsx";

export type AnyBlockProps = BlockHostProps<Record<string, never>> & Record<string, never>;

export const BLOCK_COMPONENTS: Record<string, ComponentType<AnyBlockProps>> = {
  "data.table": DataTable as unknown as ComponentType<AnyBlockProps>,
  "data.kanban": Kanban as unknown as ComponentType<AnyBlockProps>,
  "filter.bar": FilterBar as unknown as ComponentType<AnyBlockProps>,
  "metric.stat": MetricStat as unknown as ComponentType<AnyBlockProps>,
  "metric.gauge": MetricGauge as unknown as ComponentType<AnyBlockProps>,
  "record.detail": RecordDetail as unknown as ComponentType<AnyBlockProps>,
  "record.related_list": RelatedList as unknown as ComponentType<AnyBlockProps>,
  "lifecycle.pipeline": LifecyclePipeline as unknown as ComponentType<AnyBlockProps>,
  "form.record": FormRecord as unknown as ComponentType<AnyBlockProps>,
  "chart.bar": ChartBar as unknown as ComponentType<AnyBlockProps>,
  "calendar.month": CalendarMonth as unknown as ComponentType<AnyBlockProps>,
  "activity.timeline": ActivityTimeline as unknown as ComponentType<AnyBlockProps>,
  "file.list": FileList as unknown as ComponentType<AnyBlockProps>,
  "content.hero": ContentHero as unknown as ComponentType<AnyBlockProps>,
};
