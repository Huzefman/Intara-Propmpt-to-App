/**
 * Shared adapter contract (Phase 6, P6.2): every StorageAdapter passes the
 * same suite. Memory runs it directly; Dexie runs it over fake-indexeddb
 * in node (real IndexedDB in the browser).
 */
import assert from "node:assert/strict";
import type { TestContext } from "node:test";
import { VersionConflict } from "./types.ts";
import type { StorageAdapter } from "./types.ts";

export async function runContract(t: TestContext, make: () => StorageAdapter): Promise<void> {
  await t.test("put/get round-trip with auto id", async () => {
    const db = make();
    const saved = await db.put("item", { name: "mug", qty: 2 });
    assert.ok(saved["id"]);
    assert.deepEqual(await db.get("item", saved["id"] as string), saved);
    assert.equal(await db.get("item", "missing"), null);
  });

  await t.test("put overwrites by id, versions bump", async () => {
    const db = make();
    await db.put("item", { id: "a", n: 1 });
    await db.put("item", { id: "a", n: 2 }, 1);
    assert.equal((await db.get("item", "a"))?.["n"], 2);
    await assert.rejects(db.put("item", { id: "a", n: 3 }, 9), VersionConflict);
  });

  await t.test("list filter/sort/search/paginate", async () => {
    const db = make();
    await db.put("item", { id: "1", name: "mug", qty: 24, price: 12 });
    await db.put("item", { id: "2", name: "plate", qty: 3, price: 18 });
    await db.put("item", { id: "3", name: "bowl", qty: 30, price: 9 });
    let r = await db.list("item", { filter: { qty: { gte: 10 } } });
    assert.equal(r.total, 2);
    r = await db.list("item", { filter: { name: { in: ["mug", "nope"] } } });
    assert.equal(r.total, 1);
    r = await db.list("item", { filter: { name: { ne: "mug" } } });
    assert.equal(r.total, 2);
    r = await db.list("item", { filter: { qty: { lt: 10 } } });
    assert.equal(r.total, 1);
    r = await db.list("item", { sort: [{ field: "name", dir: "asc" }] });
    assert.deepEqual(r.rows.map((x) => x["id"]), ["3", "1", "2"]);
    r = await db.list("item", { sort: [{ field: "price", dir: "desc" }] });
    assert.deepEqual(r.rows.map((x) => x["id"]), ["2", "1", "3"]);
    r = await db.list("item", { search: { fields: ["name"], term: "MU" } });
    assert.equal(r.total, 1);
    r = await db.list("item", { sort: [{ field: "price", dir: "asc" }], limit: 1, offset: 1 });
    assert.equal(r.total, 3);
    assert.deepEqual(r.rows.map((x) => x["id"]), ["1"]);
    r = await db.list("other", {});
    assert.deepEqual([r.total, r.rows], [0, []]);
  });

  await t.test("remove soft-deletes", async () => {
    const db = make();
    await db.put("item", { id: "a", n: 1 });
    await db.remove("item", "a");
    assert.equal(await db.get("item", "a"), null);
    assert.equal((await db.list("item", {})).total, 0);
    await db.remove("item", "missing"); // no-op, never throws
  });

  await t.test("transaction commits and rolls back", async () => {
    const db = make();
    await db.transaction(async (tx) => {
      await tx.put("item", { id: "a", n: 1 });
    });
    assert.equal((await db.get("item", "a"))?.["n"], 1);
    await assert.rejects(db.transaction(async (tx) => {
      await tx.put("item", { id: "b", n: 2 });
      throw new Error("boom");
    }), /boom/);
    assert.equal(await db.get("item", "b"), null);
  });
}
