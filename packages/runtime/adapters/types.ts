/**
 * StorageAdapter contract (Phase 6, P6.2; shape = guide §5.2).
 * The engine wraps the adapter, so validation/refs/computed/lifecycle
 * behave identically in preview and production.
 */
export type Rec = Record<string, unknown>;

export interface FilterOps {
  eq?: unknown;
  ne?: unknown;
  gt?: number | string;
  gte?: number | string;
  lt?: number | string;
  lte?: number | string;
  in?: unknown[];
}

export interface Query {
  filter?: Record<string, unknown | FilterOps>;
  sort?: Array<{ field: string; dir: "asc" | "desc" }>;
  search?: { fields: string[]; term: string };
  limit?: number;
  offset?: number;
}

export interface Page<T> { rows: T[]; total: number }

export interface StorageAdapter {
  list(entity: string, q?: Query): Promise<Page<Rec>>;
  get(entity: string, id: string | number): Promise<Rec | null>;
  put(entity: string, rec: Rec, expectedVersion?: number): Promise<Rec>;
  remove(entity: string, id: string | number): Promise<void>;
  transaction<T>(fn: (tx: StorageAdapter) => Promise<T>): Promise<T>;
}

export class VersionConflict extends Error {
  constructor(msg: string) { super(msg); this.name = "VersionConflict"; }
}
