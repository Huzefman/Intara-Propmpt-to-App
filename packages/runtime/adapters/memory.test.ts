import { test } from "node:test";
import { runContract } from "./contract.ts";
import { MemoryAdapter } from "./memory.ts";

test("memory adapter contract", async (t) => {
  await runContract(t, () => new MemoryAdapter());
});
