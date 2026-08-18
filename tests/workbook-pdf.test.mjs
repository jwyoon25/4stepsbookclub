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
const fontsDirectory = join(repositoryRoot, "workbooks/assets/fonts");
const paginationBoundaryFixture = join(
  repositoryRoot,
  "tests/fixtures/workbook-pagination-boundary.typ",
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
      let studentWorkbookReport;
      for (const target of targets) {
        const report = await inspectWorkbookPdf(target.outputPath);
        assert.equal(
          report.pageCount,
          expectedPages.get(basename(target.outputPath)),
          basename(target.outputPath),
        );
        if (basename(target.outputPath) === "example-book-workbook-student.pdf") {
          studentWorkbookReport = report;
        }
      }

      const writingPages = studentWorkbookReport.pages.filter((page) =>
        page.headerCanonical.includes("PARAGRAPHWRITING"),
      );
      assert.deepEqual(
        writingPages.map((page) => page.ruledLines.length),
        [26, 36, 35],
      );
      for (const page of writingPages) {
        assert.ok(page.ruledLines.at(-1).pageY >= 50);
        assert.ok(page.ruledLines.at(-1).pageY <= 75);
        for (let index = 1; index < page.ruledLines.length; index += 1) {
          const gap =
            page.ruledLines[index - 1].pageY - page.ruledLines[index].pageY;
          assert.ok(Math.abs(gap - (7 * 72) / 25.4) <= 0.1);
        }
      }

      const stagedFiles = (await readdir(outputDirectory)).filter((name) =>
        name.includes(".building-"),
      );
      assert.deepEqual(stagedFiles, []);
    });
  },
);

test(
  "moves a six-line response intact when only part would fit",
  { skip: !typstAvailable },
  async () => {
    const temporaryRoot = await mkdtemp(
      join(tmpdir(), "4steps-workbook-boundary-"),
    );
    const outputPath = join(temporaryRoot, "pagination-boundary.pdf");

    try {
      const result = spawnSync(
        "typst",
        [
          "compile",
          "--root",
          repositoryRoot,
          "--font-path",
          fontsDirectory,
          paginationBoundaryFixture,
          outputPath,
        ],
        { encoding: "utf8" },
      );
      assert.equal(result.status, 0, result.stderr);

      const report = await inspectWorkbookPdf(outputPath);
      assert.equal(report.pageCount, 2);
      assert.doesNotMatch(
        report.pages[0].canonical,
        /THISSIXLINERESPONSEMUSTMOVETOTHENEXTPAGEINTACT/,
      );
      assert.match(
        report.pages[1].canonical,
        /THISSIXLINERESPONSEMUSTMOVETOTHENEXTPAGEINTACT/,
      );
      assert.equal(report.pages[0].ruledLines.length, 0);
      assert.equal(report.pages[1].ruledLines.length, 6);
    } finally {
      await rm(temporaryRoot, { recursive: true, force: true });
    }
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
