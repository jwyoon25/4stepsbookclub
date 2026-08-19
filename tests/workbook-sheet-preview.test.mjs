import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, before, describe, test } from "node:test";
import { pathToFileURL } from "node:url";

import {
  createTargetBundle,
  listWorkbookTargets,
} from "../workbooks/builder/browser/build-targets.mjs";
import {
  assertLessonLayout,
  assertSchemaValid,
  normalizeLesson,
  normalizeManifest,
} from "../workbooks/builder/browser/content-rules.mjs";
import { generateSchemaValidators } from "../workbooks/lib/browser-bundle.mjs";
import {
  createWorkbookManifest,
  locateContentPath,
  parseWorkbookGrids,
  SHEET_HEADERS,
  slugifyBookTitle,
  WorkbookSheetError,
} from "../workbooks/builder/browser/sheet-contract.mjs";
import {
  verifyWorkbookFixture,
  withVerificationDirectory,
} from "../workbooks/lib/browser-verification.mjs";
import { createWorkbookTypstCompiler } from "../workbooks/lib/typst-compiler.mjs";

const typstAvailable =
  spawnSync("typst", ["--version"], { stdio: "ignore" }).status === 0;

/** Load the generated validator the way a browser loads it: as a plain module. */
async function withGeneratedSchemaValidators() {
  const directory = await mkdtemp(join(tmpdir(), "4steps-schema-validators-"));
  const modulePath = join(directory, "schema-validators.mjs");
  try {
    await writeFile(modulePath, await generateSchemaValidators());
    return await import(pathToFileURL(modulePath).href);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

function grid(sheetName, dataRows) {
  const headers = SHEET_HEADERS[sheetName];
  const blank = () => Array.from({ length: headers.length }, () => "");
  return [
    blank(),
    blank(),
    blank(),
    [...headers],
    ...dataRows.map((row) => [
      ...row,
      ...Array.from({ length: headers.length - row.length }, () => ""),
    ]),
  ];
}

// Two lessons, every section filled, the way a tutor's Sheet looks by the time
// it is worth previewing.
function workbookGrids({ teacherGuidance = "Look for the concealed decision." } = {}) {
  const lessonNumbers = [1, 2];
  return {
    Workbook: grid("Workbook", [
      [
        "",
        "The Quiet Neighbour",
        "A. N. Author",
        "4steps Book Club Workbook",
        "Lessons 1–2",
        "A two-lesson sample",
      ],
    ]),
    Lessons: grid(
      "Lessons",
      lessonNumbers.map((number) => [
        "",
        number,
        `Lesson ${number} title`,
        `Chapters ${number}–${number + 3}`,
        "Read once for the story, then return with the questions.",
        "Support every answer with a detail from the text.",
      ]),
    ),
    Comprehension: grid(
      "Comprehension",
      lessonNumbers.map((number) => [
        "",
        number,
        1,
        "Where does the opening scene take place?",
        "",
        "Answer in 2–3 complete sentences.",
        "The setting and the elapsed time.",
      ]),
    ),
    Analysis: grid(
      "Analysis",
      lessonNumbers.map((number) => [
        "",
        number,
        1,
        "Is the narrator convincing? Explain.",
        "It was easier to say nothing at all.",
        "Write one paragraph.\nUse two quotations.",
        teacherGuidance,
      ]),
    ),
    Writing: grid(
      "Writing",
      lessonNumbers.map((number) => [
        "",
        number,
        1,
        "Defend your interpretation of the narrator.",
        "State your position directly.",
        "",
        "Claim, evidence, explanation, conclusion.",
      ]),
    ),
    Vocabulary: grid(
      "Vocabulary",
      lessonNumbers.map((number) => [
        "",
        number,
        1,
        "resolute",
        "단호한",
        "Determined and unwavering.",
        "She remained resolute even as the others reconsidered.",
        "The group has begun to doubt the plan.",
      ]),
    ),
  };
}

/**
 * The pipeline the preview window runs between the Sheet and the compiler.
 *
 * Written out here rather than imported, because what this test is checking is
 * that these separately extracted pieces still add up to a workbook.
 */
function previewWorkbook(grids) {
  const { metadata, lessons, sources } = parseWorkbookGrids(grids);
  const parsedManifest = createWorkbookManifest(metadata, lessons, {
    workbookId: slugifyBookTitle(metadata.bookTitle) || "workbook",
  });
  assertSchemaValid(schemas.validateWorkbook, parsedManifest, "the Workbook tab");
  const manifest = normalizeManifest(parsedManifest);

  const normalized = lessons.map((lesson) => {
    try {
      assertSchemaValid(schemas.validateLesson, lesson, `lesson ${lesson.lessonNumber}`);
      const normalizedLesson = normalizeLesson(lesson);
      assertLessonLayout(normalizedLesson, `lesson ${lesson.lessonNumber}`);
      return normalizedLesson;
    } catch (error) {
      error.cell = locateContentPath(sources, lesson.lessonNumber, error.path);
      throw error;
    }
  });

  return {
    manifest,
    lessons: normalized,
    targets: listWorkbookTargets(normalized),
  };
}

let compiler;
// The very module the bundle ships. Generated rather than written, so what the
// browser enforces cannot drift from what `workbooks/schema/` says.
let schemas;

before(async () => {
  ({ compiler } = await createWorkbookTypstCompiler());
  schemas = await withGeneratedSchemaValidators();
});

after(async () => {
  await compiler?.dispose();
});

test("offers every lesson and the complete workbook, in both editions", () => {
  const { targets } = previewWorkbook(workbookGrids());

  assert.deepEqual(
    targets.map(({ id }) => id),
    [
      "lesson-01-student",
      "lesson-01-teacher",
      "lesson-02-student",
      "lesson-02-teacher",
      "workbook-student",
      "workbook-teacher",
    ],
  );
  // A lesson target carries its own lesson and no other.
  assert.deepEqual(targets[0].lessonNumbers, [1]);
  assert.deepEqual(targets.at(-1).lessonNumbers, [1, 2]);
});

test("applies the response-space defaults the renderer expects", () => {
  const { lessons } = previewWorkbook(workbookGrids());
  const [lesson] = lessons;

  assert.deepEqual(lesson.sections.readingComprehension[0].responseSpace, {
    mode: "short-answer",
  });
  assert.deepEqual(lesson.sections.criticalThinkingAndAnalysis[0].responseSpace, {
    mode: "short-paragraph",
  });
  assert.deepEqual(lesson.sections.paragraphWriting[0].responseSpace, {
    mode: "full-page",
  });
});

test("refuses a Sheet with nowhere to put an answer", () => {
  // The teacher edition needs answer guidance, and the contract asks for it a
  // cell at a time rather than letting a workbook parse and fail later.
  assert.throws(
    () => previewWorkbook(workbookGrids({ teacherGuidance: "   " })),
    (error) =>
      error instanceof WorkbookSheetError &&
      error.message === '"Analysis" row 5, Teacher guidance is required.' &&
      // The same cell in numbers, so the Sheet can be made to show it.
      error.cell.sheet === "Analysis" &&
      error.cell.row === 5 &&
      error.cell.column === 7,
  );
});

test("names the cell for a problem no single column caused", () => {
  const grids = workbookGrids();
  // Two lesson rows claiming to be lesson 1: neither cell is wrong on its own.
  grids.Lessons[5][1] = 1;

  assert.throws(
    () => previewWorkbook(grids),
    (error) =>
      error instanceof WorkbookSheetError &&
      error.cell.sheet === "Lessons" &&
      error.cell.row === 6 &&
      error.cell.column === 2,
  );
});

/** Ordinary prose of a given length, so nothing trips the wrapping limit. */
function proseOf(characterCount) {
  return "the quiet argument continued into a fourth and final day "
    .repeat(Math.ceil(characterCount / 57))
    .slice(0, characterCount)
    .trim();
}

test("traces a layout failure back to the row it was typed on", () => {
  const grids = workbookGrids();
  // Lesson 2's second vocabulary entry. Every field is inside its own schema
  // limit; together they are more than one reference page holds. The rule that
  // refuses it counts characters and has never seen a spreadsheet, so the row
  // has to be recovered from the parse.
  grids.Vocabulary.push([
    "",
    2,
    2,
    "obdurate",
    "완고한",
    proseOf(600),
    proseOf(600),
    proseOf(700),
    "",
  ]);

  assert.throws(
    () => previewWorkbook(grids),
    (error) => {
      assert.equal(error.name, "WorkbookContentError");
      assert.match(error.message, /too long for the standardized workbook layout/u);
      assert.equal(error.path, "/sections/vocabulary/1");
      assert.deepEqual(error.cell, { sheet: "Vocabulary", row: 7 });
      return true;
    },
  );
});

test("traces a schema failure back to the row it was typed on", () => {
  const grids = workbookGrids();
  // The same entry with one field over its own limit. The schema catches this
  // before the layout budget gets to add anything up, and names the field.
  grids.Vocabulary.push([
    "",
    2,
    2,
    "obdurate",
    "완고한",
    "Stubbornly refusing to change an opinion.",
    proseOf(900),
    "The argument has reached its third day.",
    "",
  ]);

  assert.throws(
    () => previewWorkbook(grids),
    (error) => {
      assert.equal(error.name, "WorkbookContentError");
      assert.match(error.message, /must NOT have more than 600 characters/u);
      assert.equal(error.path, "/sections/vocabulary/1/bookExcerpt");
      assert.deepEqual(error.cell, { sheet: "Vocabulary", row: 7 });
      return true;
    },
  );
});

describe("a workbook compiled straight from Sheet values", { skip: !typstAvailable }, () => {
  test("matches what the native renderer makes of the same content", async () => {
    const { manifest, lessons, targets } = previewWorkbook(workbookGrids());
    const target = targets.find(({ id }) => id === "lesson-01-student");
    const bundle = createTargetBundle(manifest, lessons, target);

    const result = await withVerificationDirectory((directory) =>
      verifyWorkbookFixture(
        compiler,
        { ...target, id: "sheet-lesson-01-student", bundle },
        { directory },
      ),
    );

    assert.equal(result.audit.passed, true, result.audit.error);
    assert.deepEqual(result.text.differences, []);
    assert.deepEqual(result.pixels.differences, []);
    assert.equal(result.pixels.differingChannels, 0);
  });

  test("compiles the complete workbook the Sheet describes", async () => {
    const { manifest, lessons, targets } = previewWorkbook(workbookGrids());
    const target = targets.find(({ id }) => id === "workbook-teacher");
    const bundle = createTargetBundle(manifest, lessons, target);

    assert.equal(bundle.lessons.length, 2);
    assert.equal(bundle.build.scope, "workbook");

    const result = await withVerificationDirectory((directory) =>
      verifyWorkbookFixture(
        compiler,
        { ...target, id: "sheet-workbook-teacher", bundle },
        { directory, comparePixels: false },
      ),
    );

    assert.equal(result.audit.passed, true, result.audit.error);
    assert.deepEqual(result.text.differences, []);
  });
});

test("applies the schema limits the Sheet contract does not count", () => {
  const grids = workbookGrids();
  // Seven guidance lines in one cell. Nothing in the Sheet contract counts
  // them, and the layout budget has room for them; the schema caps the list at
  // six, and it is the schema that the disk build has always enforced.
  grids.Comprehension[4][5] = Array.from(
    { length: 7 },
    (_, index) => `Requirement ${index + 1}`,
  ).join("\n");

  assert.throws(
    () => previewWorkbook(grids),
    (error) => {
      assert.equal(error.name, "WorkbookContentError");
      assert.match(error.message, /must NOT have more than 6 items/u);
      assert.equal(
        error.path,
        "/sections/readingComprehension/0/responseGuidance",
      );
      // And the cell it was typed in, so the Sheet can show it.
      assert.deepEqual(error.cell, { sheet: "Comprehension", row: 5 });
      return true;
    },
  );
});

test("accepts the workbook a tutor actually typed", () => {
  const { manifest, lessons } = previewWorkbook(workbookGrids());

  assert.equal(manifest.bookTitle, "The Quiet Neighbour");
  assert.equal(lessons.length, 2);
});
