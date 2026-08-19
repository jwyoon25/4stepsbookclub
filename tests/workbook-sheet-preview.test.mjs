import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { after, before, describe, test } from "node:test";

import {
  createTargetBundle,
  listWorkbookTargets,
} from "../workbooks/builder/browser/build-targets.mjs";
import {
  assertLessonLayout,
  normalizeLesson,
  normalizeManifest,
} from "../workbooks/builder/browser/content-rules.mjs";
import {
  createWorkbookManifest,
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
  const { metadata, lessons } = parseWorkbookGrids(grids);
  const manifest = normalizeManifest(
    createWorkbookManifest(metadata, lessons, {
      workbookId: slugifyBookTitle(metadata.bookTitle) || "workbook",
    }),
  );
  const normalized = lessons.map((lesson) => {
    const normalizedLesson = normalizeLesson(lesson);
    assertLessonLayout(normalizedLesson, `lesson ${lesson.lessonNumber}`);
    return normalizedLesson;
  });

  return {
    manifest,
    lessons: normalized,
    targets: listWorkbookTargets(normalized),
  };
}

let compiler;

before(async () => {
  ({ compiler } = await createWorkbookTypstCompiler());
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
      error.message === '"Analysis" row 5, Teacher guidance is required.',
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
