/** Engine errors (fail-closed: invalid transitions/ops throw, never guess). */
export class EngineError extends Error {
  constructor(msg: string) { super(msg); this.name = "EngineError"; }
}

export type Rec = Record<string, unknown>;
