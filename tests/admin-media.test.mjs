import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { runInNewContext } from "node:vm";

const rootUrl = new URL("../", import.meta.url);

async function loadGuard() {
  const source = await readFile(
    new URL("website/public/admin/media-upload-guard.js", rootUrl),
    "utf8"
  );
  const listeners = new Map();
  const alerts = [];

  class HTMLInputElement {
    constructor(files = []) {
      this.files = files;
      this.type = "file";
      this.value = "selected";
    }
  }

  runInNewContext(source, {
    Array,
    HTMLInputElement,
    document: {
      addEventListener(type, listener, capture) {
        listeners.set(type, { listener, capture });
      }
    },
    window: {
      alert(message) {
        alerts.push(message);
      }
    }
  });

  return { alerts, HTMLInputElement, listeners };
}

function createEvent(type, target, dataTransfer) {
  return {
    type,
    target,
    dataTransfer,
    prevented: false,
    stopped: false,
    preventDefault() {
      this.prevented = true;
    },
    stopImmediatePropagation() {
      this.stopped = true;
    }
  };
}

test("admin loads the media guard before Decap", async () => {
  const html = await readFile(
    new URL("website/public/admin/index.html", rootUrl),
    "utf8"
  );

  assert.ok(
    html.indexOf("/admin/media-upload-guard.js") < html.indexOf("decap-cms.js")
  );
});

test("media guard allows files up to and including 2 MiB", async () => {
  const { alerts, HTMLInputElement, listeners } = await loadGuard();
  const input = new HTMLInputElement([
    { name: "limit.png", size: 2 * 1024 * 1024 }
  ]);
  const event = createEvent("change", input);

  assert.equal(listeners.get("change").capture, true);
  listeners.get("change").listener(event);

  assert.equal(event.prevented, false);
  assert.equal(event.stopped, false);
  assert.equal(input.value, "selected");
  assert.deepEqual(alerts, []);
});

test("media guard blocks oversized picker and drag-and-drop uploads", async () => {
  const { alerts, HTMLInputElement, listeners } = await loadGuard();
  const oversized = { name: "large.png", size: 2 * 1024 * 1024 + 1 };
  const input = new HTMLInputElement([oversized]);
  const changeEvent = createEvent("change", input);

  listeners.get("change").listener(changeEvent);

  assert.equal(changeEvent.prevented, true);
  assert.equal(changeEvent.stopped, true);
  assert.equal(input.value, "");
  assert.match(alerts[0], /최대 2MB/);
  assert.match(alerts[0], /large\.png/);

  const dropEvent = createEvent("drop", {}, { files: [oversized] });
  assert.equal(listeners.get("drop").capture, true);
  listeners.get("drop").listener(dropEvent);

  assert.equal(dropEvent.prevented, true);
  assert.equal(dropEvent.stopped, true);
  assert.equal(alerts.length, 2);
});

test("Decap stores new notice image paths relatively for draft previews", async () => {
  const config = await readFile(
    new URL("website/public/admin/config.yml", rootUrl),
    "utf8"
  );
  const contentConfig = await readFile(
    new URL("website/src/content.config.ts", rootUrl),
    "utf8"
  );

  assert.match(config, /^public_folder: images\/notices$/m);
  assert.doesNotMatch(config, /^public_folder: \/images\/notices$/m);
  assert.match(contentConfig, /path\.startsWith\("images\/notices\/"\)/);
});
