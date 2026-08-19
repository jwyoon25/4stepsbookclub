import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import JSZip from "jszip";

import {
  createTargetBundle,
  listWorkbookTargets,
  workbookPdfName,
} from "../workbooks/builder/browser/build-targets.mjs";
import { createBuildTargets } from "../workbooks/lib/build.mjs";
import { loadWorkbookPackage } from "../workbooks/lib/content.mjs";
import {
  compressPdfEntries,
  createPdfArchives,
  DEFAULT_MAX_ARCHIVE_BYTES,
  packPdfArchives,
  PdfArchiveError,
} from "../workbooks/builder/browser/pdf-archive.mjs";
import { compileWorkbookPdf } from "../workbooks/builder/browser/workbook-compiler.mjs";
import { createWorkbookTypstCompiler } from "../workbooks/lib/typst-compiler.mjs";

const moduleDirectory = dirname(fileURLToPath(import.meta.url));
const examplePackage = resolve(
  moduleDirectory,
  "../workbooks/schema/examples/example-book/workbook.json",
);

// A twelve-lesson book is what CONTENT-WORKFLOW-DECISIONS.md describes and what
// the Phase 0 gate measured the transfer against.
const REPRESENTATIVE_LESSON_COUNT = 12;

function bytes(text) {
  return new TextEncoder().encode(text);
}

async function unpack(archive) {
  const zip = await JSZip.loadAsync(archive.bytes);
  const entries = {};
  for (const name of Object.keys(zip.files)) {
    entries[name] = await zip.file(name).async("uint8array");
  }
  return entries;
}

/** Everything a twelve-lesson book owes, compiled the way the preview compiles it. */
async function compileCompleteExport(compiler) {
  const workbook = await loadWorkbookPackage(examplePackage);
  const lessons = Array.from({ length: REPRESENTATIVE_LESSON_COUNT }, (_, index) => {
    const source = workbook.lessons[index % workbook.lessons.length].content;
    return { ...structuredClone(source), lessonNumber: index + 1 };
  });
  const manifest = {
    ...workbook.manifest,
    lessonRange: `Lessons 1–${REPRESENTATIVE_LESSON_COUNT}`,
  };

  const files = [];
  for (const target of listWorkbookTargets(lessons)) {
    files.push({
      name: workbookPdfName(manifest.id, target),
      bytes: await compileWorkbookPdf(
        compiler,
        createTargetBundle(manifest, lessons, target),
      ),
    });
  }
  return files;
}

let compiler;
let exportedFiles;

before(async () => {
  ({ compiler } = await createWorkbookTypstCompiler());
  exportedFiles = await compileCompleteExport(compiler);
});

after(async () => {
  await compiler?.dispose();
});

test("an archive gives back exactly the bytes it was handed", async () => {
  const workbookPdf = exportedFiles.find(({ name }) =>
    name.endsWith("-workbook-student.pdf"),
  );

  const [archive] = await createPdfArchives([
    workbookPdf,
    // A book titled in Hangul slugs to a name that is not ASCII, so entry names
    // have to survive the round trip as UTF-8.
    { name: "한글-lesson-01-teacher.pdf", bytes: bytes("not really a PDF") },
  ]);

  const entries = await unpack(archive);
  assert.deepEqual(Object.keys(entries).sort(), [
    workbookPdf.name,
    "한글-lesson-01-teacher.pdf",
  ]);
  assert.deepEqual(entries[workbookPdf.name], workbookPdf.bytes);
  assert.deepEqual(entries["한글-lesson-01-teacher.pdf"], bytes("not really a PDF"));
  assert.ok(
    archive.bytes.length < workbookPdf.bytes.length,
    `a compressed archive should be smaller than the PDF alone; got ${archive.bytes.length}`,
  );
});

test("splits into as few archives as the budget allows", async () => {
  const entries = await compressPdfEntries(
    Array.from({ length: 6 }, (_, index) => ({
      name: `book-lesson-0${index + 1}-student.pdf`,
      // Random bytes so deflate cannot collapse them and each entry really does
      // weigh what the budget is being asked to divide.
      bytes: crypto.getRandomValues(new Uint8Array(40_000)),
    })),
  );

  const archives = packPdfArchives(entries, { maxArchiveBytes: 100_000 });
  assert.equal(archives.length, 3);
  assert.deepEqual(
    archives.flatMap(({ names }) => names),
    entries.map(({ name }) => name),
  );
  for (const archive of archives) {
    assert.equal(archive.names.length, 2);
  }
});

test("still exports a PDF larger than the whole budget", async () => {
  const archives = await createPdfArchives(
    [
      {
        name: "book-workbook-student.pdf",
        bytes: crypto.getRandomValues(new Uint8Array(20_000)),
      },
    ],
    { maxArchiveBytes: 1000 },
  );

  assert.equal(archives.length, 1);
  assert.deepEqual(archives[0].names, ["book-workbook-student.pdf"]);
});

test("refuses an entry that is not PDF bytes", async () => {
  await assert.rejects(
    () => createPdfArchives([{ name: "book.pdf", bytes: "a string of PDF" }]),
    PdfArchiveError,
  );
});

test("names exported PDFs the way the native renderer names them on disk", async () => {
  const workbook = await loadWorkbookPackage(examplePackage);
  const onDisk = createBuildTargets(workbook, "/anywhere")
    .map(({ outputPath }) => outputPath.split("/").at(-1))
    .sort();
  const fromTheBrowser = listWorkbookTargets(
    workbook.lessons.map(({ content }) => content),
  )
    .map((target) => workbookPdfName(workbook.manifest.id, target))
    .sort();

  assert.deepEqual(fromTheBrowser, onDisk);
});

test("sends a whole book in a handful of calls rather than one per file", async () => {
  assert.equal(exportedFiles.length, 26);

  const archives = await createPdfArchives(exportedFiles, {
    maxArchiveBytes: DEFAULT_MAX_ARCHIVE_BYTES,
  });
  assert.ok(
    archives.length <= 3,
    `a twelve-lesson book should not cost more than three calls; got ${archives.length}`,
  );

  // Every PDF has to arrive, and arrive whole: Drive gets whatever the archives
  // hold, and nothing on the far side re-checks them.
  const unpacked = {};
  for (const archive of archives) {
    Object.assign(unpacked, await unpack(archive));
  }
  assert.deepEqual(
    Object.keys(unpacked).sort(),
    exportedFiles.map(({ name }) => name).sort(),
  );
  for (const { name, bytes: original } of exportedFiles) {
    assert.deepEqual(unpacked[name], original, `${name} did not survive the archive`);
  }
});
