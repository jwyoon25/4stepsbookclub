import assert from "node:assert/strict";
import test from "node:test";

import {
  createWorkbookManifest,
  parseWorkbookGrids,
  SHEET_HEADERS,
  slugifyBookTitle,
  WorkbookSheetError,
} from "../workbooks/builder/browser/sheet-contract.mjs";

// Apps Script hands over exactly this: rectangular arrays of primitives, with
// the template's own header row where the template puts it.
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

function workbookGrids(overrides = {}) {
  return {
    Workbook: grid("Workbook", [
      [
        "",
        "The Example Book",
        "A. N. Author",
        "4steps Book Club Workbook",
        "Lesson 3",
        "A schema example",
      ],
    ]),
    Lessons: grid("Lessons", [
      ["", 3, "What the Narrator Leaves Out", "Chapters 9–13", "Read once.", "Cite the text."],
    ]),
    Comprehension: grid("Comprehension", [
      ["", 3, 1, "Where does the opening scene take place?", "", "", "The setting and the elapsed time."],
    ]),
    Analysis: grid("Analysis", [
      ["", 3, 1, "Is the narrator convincing?", "", "One paragraph.\nTwo quotations.", "Either position, if supported."],
    ]),
    Writing: grid("Writing", [["", 3, 1, "Defend your interpretation."]]),
    Vocabulary: grid("Vocabulary", [
      ["", 3, 1, "resolute", "단호한", "Determined and unwavering.", "She remained resolute.", "The others reconsider."],
    ]),
    ...overrides,
  };
}

test("converts live Sheet values into schema-v1 content", () => {
  const { metadata, lessons } = parseWorkbookGrids(workbookGrids());

  assert.deepEqual(metadata, {
    bookTitle: "The Example Book",
    author: "A. N. Author",
    seriesTitle: "4steps Book Club Workbook",
    lessonRange: "Lesson 3",
    coverSubtitle: "A schema example",
  });
  assert.equal(lessons.length, 1);

  const [lesson] = lessons;
  assert.equal(lesson.schemaVersion, 1);
  assert.equal(lesson.lessonNumber, 3);
  assert.equal(lesson.title, "What the Narrator Leaves Out");
  assert.equal(lesson.framingNote, "Read once.");
  assert.equal(
    lesson.sections.readingComprehension[0].prompt,
    "Where does the opening scene take place?",
  );
  // One guidance item per line, which is how the column asks tutors to write it.
  assert.deepEqual(lesson.sections.criticalThinkingAndAnalysis[0].responseGuidance, [
    "One paragraph.",
    "Two quotations.",
  ]);
  assert.equal(lesson.sections.vocabulary[0].koreanMeaning, "단호한");
  // Defaults belong to the renderer, so an unset response space stays unset.
  assert.equal(lesson.sections.paragraphWriting[0].responseSpace, undefined);
});

test("accepts numbers a Sheet returns as text", () => {
  const grids = workbookGrids({
    Lessons: grid("Lessons", [["", "3", "Lesson three", "Chapters 9–13"]]),
  });

  const { lessons } = parseWorkbookGrids(grids);

  assert.equal(lessons[0].lessonNumber, 3);
});

test("names the tab, row, and column of a missing required cell", () => {
  const grids = workbookGrids({
    Comprehension: grid("Comprehension", [["", 3, 1, "A question with no answer key."]]),
  });

  assert.throws(
    () => parseWorkbookGrids(grids),
    (error) =>
      error instanceof WorkbookSheetError &&
      error.message === '"Comprehension" row 5, Teacher guidance is required.',
  );
});

test("rejects a renamed column", () => {
  const rows = grid("Lessons", [["", 3, "Lesson three", "Chapters 9–13"]]);
  rows[3][2] = "Lesson name";

  assert.throws(
    () => parseWorkbookGrids(workbookGrids({ Lessons: rows })),
    (error) =>
      error instanceof WorkbookSheetError &&
      error.message ===
        '"Lessons" column 3 must be named "Lesson title"; found "Lesson name".',
  );
});

test("rejects a missing tab", () => {
  const grids = workbookGrids();
  delete grids.Vocabulary;

  assert.throws(
    () => parseWorkbookGrids(grids),
    (error) =>
      error instanceof WorkbookSheetError &&
      /Required tab "Vocabulary" is missing/.test(error.message),
  );
});

test("rejects a date where a Sheet should hold text", () => {
  // A tutor who types 9-13 into an unformatted cell gets a date back from
  // Google, and a date is not a chapter range.
  const grids = workbookGrids({
    Lessons: grid("Lessons", [["", 3, "Lesson three", new Date("2026-09-13")]]),
  });

  assert.throws(
    () => parseWorkbookGrids(grids),
    (error) =>
      error instanceof WorkbookSheetError &&
      error.message === '"Lessons" row 5, Chapter or page range must contain text.',
  );
});

test("holds the response-space rules the template dropdown implies", () => {
  const withoutLineCount = workbookGrids({
    Writing: grid("Writing", [
      ["", 3, 1, "Defend your interpretation.", "", "", "", "Custom lines"],
    ]),
  });
  assert.throws(
    () => parseWorkbookGrids(withoutLineCount),
    (error) =>
      error instanceof WorkbookSheetError &&
      error.message === '"Writing" row 5, Custom lines is required for Custom lines.',
  );

  const withLineCount = workbookGrids({
    Writing: grid("Writing", [
      ["", 3, 1, "Defend your interpretation.", "", "", "", "Custom lines", 5],
    ]),
  });
  const { lessons } = parseWorkbookGrids(withLineCount);
  assert.deepEqual(lessons[0].sections.paragraphWriting[0].responseSpace, {
    mode: "custom-lines",
    lines: 5,
  });

  const withoutResponseLines = workbookGrids({
    Comprehension: grid("Comprehension", [
      [
        "",
        3,
        1,
        "Choose the best answer.",
        "",
        "",
        "Accept the correct choice.",
        "Custom lines",
        0,
      ],
    ]),
  });
  const zeroLineResult = parseWorkbookGrids(withoutResponseLines);
  assert.deepEqual(
    zeroLineResult.lessons[0].sections.readingComprehension[0].responseSpace,
    { mode: "custom-lines", lines: 0 },
  );
});

test("orders section items by their Order column, not by row", () => {
  const grids = workbookGrids({
    Comprehension: grid("Comprehension", [
      ["", 3, 2, "Second question.", "", "", "Guidance."],
      ["", 3, 1, "First question.", "", "", "Guidance."],
    ]),
  });

  const { lessons } = parseWorkbookGrids(grids);

  assert.deepEqual(
    lessons[0].sections.readingComprehension.map(({ prompt }) => prompt),
    ["First question.", "Second question."],
  );
});

test("builds a manifest that points at one file per lesson", () => {
  const { metadata, lessons } = parseWorkbookGrids(workbookGrids());

  const manifest = createWorkbookManifest(metadata, lessons, {
    workbookId: "example-book",
  });

  assert.equal(manifest.id, "example-book");
  assert.equal(manifest.bookTitle, "The Example Book");
  assert.deepEqual(manifest.lessonFiles, ["lessons/lesson-03.json"]);
  assert.throws(
    () => createWorkbookManifest(metadata, lessons, { workbookId: "Example Book" }),
    WorkbookSheetError,
  );
});

test("slugs a title, and says so when it cannot", () => {
  assert.equal(slugifyBookTitle("The Maze Runner"), "the-maze-runner");
  assert.equal(slugifyBookTitle("Café Brulé"), "cafe-brule");
  // Nothing sluggable: the caller has to choose an identifier.
  assert.equal(slugifyBookTitle("메이즈 러너"), "");
});
