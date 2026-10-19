/** CSV round-trip tests (Phase 8, slice 2): quoting, BOM, empty, ids. */
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseCsv, toCsv } from "./csv.ts";

test("csv export quotes and skips id column dup", () => {
  const out = toCsv([
    { id: "a", name: 'Say "hi", ok', qty: 2 },
    { id: "b", name: "plain", qty: null },
  ]);
  const lines = out.split("\n");
  assert.equal(lines[0], "id,name,qty");
  assert.equal(lines[1], 'a,"Say ""hi"", ok",2');
  assert.equal(lines[2], "b,plain,");
});

test("csv import parses quotes, commas, BOM, blank lines", () => {
  const rows = parseCsv('\uFEFFid,name,qty\n1,"a, b",3\n\n2,plain,\n');
  assert.equal(rows.length, 2);
  assert.equal(rows[0]["name"], "a, b");
  assert.equal(rows[0]["qty"], "3");
  assert.equal(rows[1]["qty"], "");
  assert.equal(rows[0]["id"], "1", "a real id column round-trips");
});

test("csv import leaves id-less rows id-less (adapter mints unique ids)", () => {
  const rows = parseCsv("name,qty\nWidget,3\nGadget,4\n");
  assert.equal(rows.length, 2);
  assert.equal(rows[0]["id"], undefined);
  assert.equal(rows[1]["id"], undefined);
  assert.equal(rows[0]["name"], "Widget");
});

test("csv round-trips through parse", () => {
  const rows = [{ id: "x", title: "hello", n: 1 }];
  const back = parseCsv(toCsv(rows));
  assert.equal(back.length, 1);
  assert.equal(back[0]["id"], "x");
  assert.equal(back[0]["title"], "hello");
  assert.equal(back[0]["n"], "1", "csv values are strings; engine coerces");
});

test("csv empty input", () => {
  assert.deepEqual(parseCsv(""), []);
  assert.deepEqual(parseCsv("   \n  "), []);
  assert.equal(toCsv([]), "");
});
