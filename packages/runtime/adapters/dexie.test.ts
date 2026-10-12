import { test } from "node:test";
import { indexedDB, IDBKeyRange } from "fake-indexeddb";
import { Dexie } from "dexie";
import { runContract } from "./contract.ts";
import { DexieAdapter } from "./dexie.ts";

Dexie.dependencies.indexedDB = indexedDB;
Dexie.dependencies.IDBKeyRange = IDBKeyRange;

let n = 0;
test("dexie adapter contract", async (t) => {
  await runContract(t, () => new DexieAdapter(`intara-test-${Date.now()}-${n++}`));
});
