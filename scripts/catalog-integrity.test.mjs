import assert from "node:assert/strict";
import { existsSync, openSync, readFileSync, readSync, closeSync } from "node:fs";
import { test } from "node:test";

const catalog = JSON.parse(
  readFileSync(new URL("../src/data/catalog.json", import.meta.url), "utf8"),
);

const UUID_RE =
  /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

test("catalog file URLs are well-formed and carry no scraped JSON fragments", () => {
  for (const item of catalog.items) {
    for (const file of item.files) {
      assert.doesNotMatch(file.url, /["'\\]|richtextProperties/, `${item.id} ${file.filename}`);
      assert.doesNotThrow(() => new URL(file.url), `${item.id} ${file.url}`);
    }
  }
});

test("every catalog file has a live/dead status and a known size", () => {
  for (const item of catalog.items) {
    for (const file of item.files) {
      assert.ok(file.status === "live" || file.status === "dead", `${item.id} ${file.filename}`);
      assert.ok(Number.isFinite(file.bytes) && file.bytes > 0, `${item.id} ${file.filename}`);
    }
  }
});

test("no item lists the same DAM asset twice", () => {
  for (const item of catalog.items) {
    const seen = new Set();
    for (const file of item.files) {
      const uuid = file.url.match(UUID_RE)?.[0]?.toLowerCase() ?? file.url;
      assert.ok(!seen.has(uuid), `${item.id} repeats ${uuid}`);
      seen.add(uuid);
    }
  }
});

test("every downloaded local copy exists and is not an HTML page", () => {
  for (const item of catalog.items) {
    for (const file of item.files) {
      if (!file.downloaded || !file.publicPath) continue;
      const disk = new URL(`../public${file.publicPath}`, import.meta.url);
      assert.ok(existsSync(disk), `${item.id} missing ${file.publicPath}`);
      const fd = openSync(disk, "r");
      const head = Buffer.alloc(5);
      try {
        readSync(fd, head, 0, 5, 0);
      } finally {
        closeSync(fd);
      }
      if (/\.pdf$/i.test(file.publicPath)) {
        assert.equal(head.toString("latin1"), "%PDF-", `${item.id} ${file.publicPath}`);
      } else {
        assert.notEqual(head.toString("latin1"), "<!DOC", `${item.id} ${file.publicPath}`);
      }
    }
  }
});
