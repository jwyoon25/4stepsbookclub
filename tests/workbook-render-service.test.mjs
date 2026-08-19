import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import JSZip from "jszip";

import { renderWorkbookArchive } from "../workbooks/service/render-archive.mjs";
import { createWorkbookRenderServer } from "../workbooks/service/server.mjs";

const repositoryRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const templatePath = join(
  repositoryRoot,
  "outputs/2026-08-19-google-sheets-mvp/4steps-workbook-authoring-template.xlsx",
);
const token = "test-renderer-token-that-is-longer-than-32-characters";
const xlsxContentType =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

async function listen(server) {
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  return `http://127.0.0.1:${address.port}`;
}

async function close(server) {
  await new Promise((resolve, reject) =>
    server.close((error) => (error ? reject(error) : resolve())),
  );
}

test("packages every audited workbook PDF for the Sheets automation", async () => {
  const result = await renderWorkbookArchive(await readFile(templatePath), {
    workbookId: "example-book",
  });
  const archive = await JSZip.loadAsync(result.archive);
  const files = Object.values(archive.files)
    .filter((entry) => !entry.dir)
    .map((entry) => entry.name)
    .sort();

  assert.equal(result.workbookId, "example-book");
  assert.equal(result.lessonCount, 1);
  assert.deepEqual(result.pdfNames.sort(), [
    "example-book-lesson-03-student.pdf",
    "example-book-lesson-03-teacher.pdf",
    "example-book-workbook-student.pdf",
    "example-book-workbook-teacher.pdf",
  ]);
  assert.deepEqual(files, ["build.json", ...result.pdfNames].sort());
  const build = JSON.parse(await archive.file("build.json").async("string"));
  assert.equal(build.bookTitle, "The Example Book");
  assert.deepEqual(build.pdfFiles.sort(), result.pdfNames);
});

test("exposes authenticated render and unauthenticated health endpoints", async () => {
  const renderCalls = [];
  const server = createWorkbookRenderServer({
    token,
    render: async (body, options) => {
      renderCalls.push({ body: body.toString("utf8"), options });
      return {
        archive: Buffer.from("zip-result"),
        pdfNames: ["book-workbook-student.pdf"],
        workbookId: "book",
      };
    },
  });
  const baseUrl = await listen(server);

  try {
    const health = await fetch(`${baseUrl}/healthz`);
    assert.equal(health.status, 200);
    assert.deepEqual(await health.json(), { ok: true });

    const unauthorized = await fetch(`${baseUrl}/render`, {
      method: "POST",
      headers: { "Content-Type": xlsxContentType },
      body: "workbook",
    });
    assert.equal(unauthorized.status, 401);

    const rendered = await fetch(`${baseUrl}/render`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": xlsxContentType,
        "X-Workbook-Id": "book",
      },
      body: "workbook",
    });
    assert.equal(rendered.status, 200);
    assert.equal(rendered.headers.get("content-type"), "application/zip");
    assert.equal(rendered.headers.get("x-workbook-id"), "book");
    assert.equal(rendered.headers.get("x-pdf-count"), "1");
    assert.equal(Buffer.from(await rendered.arrayBuffer()).toString(), "zip-result");
    assert.deepEqual(renderCalls, [
      { body: "workbook", options: { workbookId: "book" } },
    ]);
  } finally {
    await close(server);
  }
});
