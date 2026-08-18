import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { cp, mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { buildWorkbookPdfs } from "../workbooks/lib/build.mjs";
import { inspectWorkbookPdf } from "../workbooks/lib/pdf-audit.mjs";

const repositoryRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const examplePackage = join(
  repositoryRoot,
  "workbooks/schema/examples/example-book",
);
const typstAvailable =
  spawnSync("typst", ["--version"], { stdio: "ignore" }).status === 0;

async function readJson(filePath) {
  return JSON.parse(await readFile(filePath, "utf8"));
}

async function writeJson(filePath, value) {
  await writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`);
}

async function withPdfPackage(run) {
  const temporaryRoot = await mkdtemp(join(tmpdir(), "4steps-workbook-pdf-"));
  const packageDirectory = join(temporaryRoot, "example-book");
  const outputDirectory = join(temporaryRoot, "output");
  await cp(examplePackage, packageDirectory, { recursive: true });

  try {
    return await run({
      packageDirectory,
      outputDirectory,
      manifestPath: join(packageDirectory, "workbook.json"),
      lessonPath: join(packageDirectory, "lessons/lesson-03.json"),
    });
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
}

test(
  "renders and audits every canonical workbook PDF",
  { skip: !typstAvailable },
  async () => {
    await withPdfPackage(async ({ manifestPath, outputDirectory }) => {
      const targets = await buildWorkbookPdfs(manifestPath, { outputDirectory });
      const expectedPages = new Map([
        ["example-book-workbook-student.pdf", 9],
        ["example-book-lesson-03-student.pdf", 8],
        ["example-book-workbook-teacher.pdf", 7],
        ["example-book-lesson-03-teacher.pdf", 6],
      ]);

      assert.equal(targets.length, expectedPages.size);
      for (const target of targets) {
        const report = await inspectWorkbookPdf(target.outputPath);
        assert.equal(
          report.pageCount,
          expectedPages.get(basename(target.outputPath)),
          basename(target.outputPath),
        );
      }

      const stagedFiles = (await readdir(outputDirectory)).filter((name) =>
        name.includes(".building-"),
      );
      assert.deepEqual(stagedFiles, []);
    });
  },
);

test(
  "keeps page totals and continuation labels stable under pagination stress",
  { skip: !typstAvailable },
  async () => {
    await withPdfPackage(
      async ({ manifestPath, lessonPath, outputDirectory }) => {
        const lesson = await readJson(lessonPath);
        lesson.sections.readingComprehension[0].responseSpace = {
          mode: "custom-lines",
          lines: 70,
        };
        lesson.sections.criticalThinkingAndAnalysis[0].responseSpace = {
          mode: "multiple-pages",
          pages: 4,
        };
        lesson.sections.paragraphWriting[0].responseSpace = {
          mode: "multiple-pages",
          pages: 4,
        };
        lesson.sections.vocabulary = Array.from({ length: 35 }, (_, index) => ({
          term: `term-${String(index + 1).padStart(2, "0")}`,
          koreanMeaning: `뜻 ${index + 1}`,
          definition: `Definition ${index + 1} wraps predictably in the standard field.`,
          bookExcerpt: `Book excerpt ${index + 1} is a stable pagination fixture.`,
          excerptContext: `Context ${index + 1} explains the surrounding chapter moment.`,
          chapterReference: `Chapter ${index + 1}`,
        }));
        await writeJson(lessonPath, lesson);

        const targets = await buildWorkbookPdfs(manifestPath, { outputDirectory });
        const studentWorkbook = targets.find(
          ({ scope, edition }) => scope === "workbook" && edition === "student",
        );
        const report = await inspectWorkbookPdf(studentWorkbook.outputPath);
        const continuationCount = report.pages.reduce(
          (count, page) =>
            count + (page.text.match(/Question\s+\d+\s+Continued/g) ?? []).length,
          0,
        );

        assert.ok(report.pageCount >= 20);
        assert.ok(continuationCount >= 9);
        assert.match(report.pages.at(-1).canonical, /VOCABULARY/);
      },
    );
  },
);
