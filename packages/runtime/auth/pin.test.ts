/** PIN lock tests (Phase 8): enroll/verify/wrong-pin/format/clear, adapter-backed. */
import { test } from "node:test";
import assert from "node:assert/strict";
import { MemoryAdapter } from "../adapters/memory.ts";
import { clearPin, enrollPin, hashPin, isEnrolled, newSalt, validPinFormat, verifyPin } from "./pin.ts";

test("pin lifecycle: enroll, verify, wrong pin fails, clear", async () => {
  const db = new MemoryAdapter();
  assert.equal(await isEnrolled(db), false);
  assert.equal(await verifyPin(db, "1234"), false);
  await enrollPin(db, "1234");
  assert.equal(await isEnrolled(db), true);
  assert.equal(await verifyPin(db, "1234"), true);
  assert.equal(await verifyPin(db, "0000"), false);
  assert.equal(await verifyPin(db, ""), false);
  await clearPin(db);
  assert.equal(await isEnrolled(db), false);
});

test("pin format and hashing", async () => {
  assert.equal(validPinFormat("1234"), true);
  assert.equal(validPinFormat("12345678"), true);
  assert.equal(validPinFormat("123"), false);
  assert.equal(validPinFormat("123456789"), false);
  assert.equal(validPinFormat("12ab"), false);
  const s1 = newSalt(), s2 = newSalt();
  assert.notEqual(s1, s2);
  assert.notEqual(await hashPin("1234", s1), await hashPin("1234", s2));
  await assert.rejects(enrollPin(new MemoryAdapter(), "12"), /4–8 digits/);
});
