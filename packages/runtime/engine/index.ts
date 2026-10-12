/** Runtime engine public surface (Phase 6, P6.1). */
export { EngineError } from "./errors.ts";
export type { Rec } from "./errors.ts";
export { validateRecord } from "./validate.ts";
export type { FieldError } from "./validate.ts";
export { applyDefaults } from "./defaults.ts";
export { computeRecord } from "./computed.ts";
export type { ComputedError } from "./computed.ts";
export { checkRefsExist, enforceOnDelete } from "./refs.ts";
export type { RefStore, RefError } from "./refs.ts";
export { allowedTransitions, applyTransition } from "./lifecycle.ts";
export type { TransitionCtx } from "./lifecycle.ts";
export { can } from "./permissions.ts";
export type { UserCtx } from "./permissions.ts";
