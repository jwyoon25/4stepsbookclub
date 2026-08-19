import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import ExcelJS from "exceljs";

import { loadWorkbookPackage } from "../workbooks/lib/content.mjs";
import {
  readWorkbookSheet,
  WorkbookSheetError,
  writeWorkbookPackage,
} from "../workbooks/lib/sheet-import.mjs";

const repositoryRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const templatePath = join(
  repositoryRoot,
  "outputs/2026-08-19-google-sheets-mvp/4steps-workbook-authoring-template.xlsx",
);
const examplePackage = join(
  repositoryRoot,
  "workbooks/schema/examples/example-book",
);

async function readJson(filePath) {
  return JSON.parse(await readFile(filePath, "utf8"));
}

test("imports the Google Sheets template as the canonical schema-v1 package", async () => {
  const sheetPackage = await readWorkbookSheet(templatePath, {
    workbookId: "example-book",
  });
  const expectedManifest = await readJson(join(examplePackage, "workbook.json"));
  const expectedLesson = await readJson(
    join(examplePackage, "lessons/lesson-03.json"),
  );
  expectedManifest.$schema = "../../schema/workbook.schema.json";
  expectedLesson.$schema = "../../../schema/lesson.schema.json";

  assert.deepEqual(sheetPackage.manifest, expectedManifest);
  assert.deepEqual(sheetPackage.lessons, [expectedLesson]);
  assert.equal(
    Object.hasOwn(
      sheetPackage.lessons[0].sections.paragraphWriting[0],
      "hints",
    ),
    false,
  );

  const temporaryRoot = await mkdtemp(join(tmpdir(), "4steps-sheet-test-"));
  const outputDirectory = join(temporaryRoot, "example-book");
  try {
    const result = await writeWorkbookPackage(sheetPackage, outputDirectory);
    const workbook = await loadWorkbookPackage(result.manifestPath);

    assert.equal(result.lessonCount, 1);
    assert.equal(workbook.manifest.id, "example-book");
    assert.deepEqual(
      workbook.lessons.map(({ content }) => content.lessonNumber),
      [3],
    );
    assert.deepEqual(
      workbook.lessons[0].content.sections.readingComprehension[1]
        .responseSpace,
      { mode: "custom-lines", lines: 5 },
    );
    assert.deepEqual(
      workbook.lessons[0].content.sections.paragraphWriting[1].responseSpace,
      { mode: "multiple-pages", pages: 2 },
    );
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
});

test("rejects response-space numbers without a matching dropdown choice", async () => {
  const temporaryRoot = await mkdtemp(join(tmpdir(), "4steps-sheet-invalid-"));
  const invalidPath = join(temporaryRoot, "invalid.xlsx");
  try {
    const workbook = new ExcelJS.Workbook();
    await workbook.xlsx.readFile(templatePath);
    workbook.getWorksheet("Comprehension").getCell("I5").value = 4;
    await workbook.xlsx.writeFile(invalidPath);

    await assert.rejects(
      readWorkbookSheet(invalidPath),
      (error) => {
        assert.ok(error instanceof WorkbookSheetError);
        assert.match(error.message, /"Comprehension" row 5, Response space/);
        assert.match(error.message, /must be set/);
        return true;
      },
    );
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
});

test("rejects duplicate section order within a lesson", async () => {
  const temporaryRoot = await mkdtemp(join(tmpdir(), "4steps-sheet-order-"));
  const invalidPath = join(temporaryRoot, "invalid.xlsx");
  try {
    const workbook = new ExcelJS.Workbook();
    await workbook.xlsx.readFile(templatePath);
    workbook.getWorksheet("Analysis").getCell("C6").value = 1;
    await workbook.xlsx.writeFile(invalidPath);

    await assert.rejects(
      readWorkbookSheet(invalidPath),
      (error) => {
        assert.ok(error instanceof WorkbookSheetError);
        assert.match(error.message, /"Analysis" row 6 duplicates order 1/);
        return true;
      },
    );
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
});
