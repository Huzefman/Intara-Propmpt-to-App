/** Upload path tests (Phase 8, slice 3): naming + fake-client round-trip. */
import { test } from "node:test";
import assert from "node:assert/strict";
import { objectPath, uploadBlob, UPLOAD_BUCKET } from "./uploads.ts";

test("object paths are namespaced, sanitized, unique", () => {
  const a = objectPath("receipt", "My Invoice #1.PDF");
  const b = objectPath("receipt", "My Invoice #1.PDF");
  assert.ok(a.startsWith("receipt/"));
  assert.ok(!a.includes(" ") && !a.includes("#"));
  assert.ok(a.endsWith("-my-invoice-1.pdf"));
  assert.notEqual(a, b);
});

test("upload round-trips through a fake client", async () => {
  const seen: Array<{ bucket: string; path: string }> = [];
  const fake = {
    storage: {
      from: (bucket: string) => ({
        upload: async (path: string, _body: unknown) => {
          seen.push({ bucket, path });
          return { error: null };
        },
        getPublicUrl: (path: string) => ({ data: { publicUrl: `https://cdn/x/${path}` } }),
      }),
    },
  };
  const url = await uploadBlob(fake, "doc", "a.txt", "hello");
  assert.equal(seen.length, 1);
  assert.equal(seen[0].bucket, UPLOAD_BUCKET);
  assert.ok(url.startsWith("https://cdn/x/doc/"));
});

test("upload surfaces provider errors", async () => {
  const fake = {
    storage: {
      from: (_b: string) => ({
        upload: async (_p: string, _o: unknown) => ({ error: { message: "denied" } }),
        getPublicUrl: (_p: string) => ({ data: { publicUrl: "" } }),
      }),
    },
  };
  await assert.rejects(uploadBlob(fake, "doc", "a.txt", "x"), /denied/);
});
