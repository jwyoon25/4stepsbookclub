// ---------------------------------------------------------------------------
// What a workbook's content means before anything renders it.
//
// Two jobs, both of which have to give the same answer wherever content comes
// from: filling in the defaults an author did not state, and refusing content
// that cannot fit the standardized layout. A preview compiled in the browser
// from a live Sheet and a PDF built from files on disk have to agree about both,
// or the preview stops being a preview.
//
// Like the Sheet contract, this imports nothing. The filesystem, the JSON
// schemas, and the package layout stay in `lib/content.mjs`, which is the only
// caller that has files to read.
//
// Every message names a location — a file path from disk, a lesson from a
// Sheet — because the author has to be told where to look.
// ---------------------------------------------------------------------------

const DEFAULT_RESPONSE_SPACES = Object.freeze({
  readingComprehension: Object.freeze({ mode: "short-answer" }),
  criticalThinkingAndAnalysis: Object.freeze({ mode: "short-paragraph" }),
  paragraphWriting: Object.freeze({ mode: "full-page" }),
});
const DEFAULT_SERIES_TITLE = "4steps Book Club Workbook";

// Layout validation reserves at least this many first-page lines. Full-page
// modes render additional lines dynamically when the page has room.
const MINIMUM_FIRST_PAGE_LINE_COUNTS = Object.freeze({
  "short-answer": 3,
  "short-paragraph": 6,
  "extended-answer": 12,
  "full-page": 14,
  "multiple-pages": 14,
});
const RESPONSE_LINE_LAYOUT_UNITS = 54;

const MAX_LESSON_COVER_UNITS = 700;
const MAX_VOCABULARY_ENTRY_UNITS = 1900;
const MAX_UNBROKEN_TEXT_UNITS = 80;

/**
 * Content that cannot be laid out, wherever it came from.
 *
 * The message says which lesson and which field, because that is what an author
 * needs read to them. `path` repeats the field on its own, so a caller that
 * knows where the content was typed — a Sheet row, a file on disk — can point
 * at it directly. This file never learns which of those it is.
 */
export class WorkbookContentError extends Error {
  constructor(message, { path, ...options } = {}) {
    super(message, options);
    this.name = "WorkbookContentError";
    this.path = path;
  }
}

/**
 * Where a schema validator was pointing.
 *
 * Ajv reports a missing or unexpected property against the object that should
 * have held it, so the property's own name is appended; everything else already
 * addresses the value that failed.
 */
function schemaLocation(error) {
  const instancePath = error.instancePath === "/" ? "" : error.instancePath;
  if (error.keyword === "required") {
    return `${instancePath}/${error.params.missingProperty}`;
  }
  if (error.keyword === "additionalProperties") {
    return `${instancePath}/${error.params.additionalProperty}`;
  }
  return instancePath || "/";
}

/**
 * Refuse content the JSON schemas reject.
 *
 * The schemas hold the limits nothing else does — how long a prompt may be, how
 * many guidance lines an item may carry — and they are the same limits wherever
 * the content came from. The caller supplies a compiled validator, because
 * compiling one needs a schema loader that a browser and a filesystem do
 * differently; what a failure means is decided here.
 */
export function assertSchemaValid(validator, value, source) {
  if (validator(value)) {
    return;
  }

  const errors = validator.errors ?? [];
  const details = errors
    .map((error) => `  ${schemaLocation(error)}: ${error.message ?? "is invalid"}`)
    .join("\n");

  throw new WorkbookContentError(
    `Content does not match the schema in ${source}:\n${details}`,
    { path: errors.length > 0 ? schemaLocation(errors[0]) : undefined },
  );
}

/** Apply the response-space defaults and fold legacy hints into guidance. */
export function normalizeLesson(lesson) {
  const normalized = structuredClone(lesson);

  for (const question of normalized.sections.readingComprehension) {
    question.responseSpace ??= {
      ...DEFAULT_RESPONSE_SPACES.readingComprehension,
    };
  }

  for (const question of normalized.sections.criticalThinkingAndAnalysis) {
    question.responseSpace ??= {
      ...DEFAULT_RESPONSE_SPACES.criticalThinkingAndAnalysis,
    };
  }

  for (const prompt of normalized.sections.paragraphWriting) {
    if (prompt.hints) {
      prompt.responseGuidance = [
        ...(prompt.responseGuidance ?? []),
        ...prompt.hints,
      ];
      delete prompt.hints;
    }
    prompt.responseSpace ??= {
      ...DEFAULT_RESPONSE_SPACES.paragraphWriting,
    };
  }

  return normalized;
}

export function normalizeManifest(manifest) {
  const normalized = structuredClone(manifest);
  normalized.seriesTitle ??= DEFAULT_SERIES_TITLE;
  return normalized;
}

function layoutUnits(value) {
  let units = 0;
  for (const character of value ?? "") {
    if (character === "\n") {
      units += 60;
    } else if (/\p{Script=Hangul}|\p{Script=Han}/u.test(character)) {
      units += 2;
    } else {
      units += 1;
    }
  }
  return units;
}

function assertLayoutBudget(source, location, actual, maximum, guidance) {
  if (actual <= maximum) {
    return;
  }

  throw new WorkbookContentError(
    `Content is too long for the standardized workbook layout in ${source}:\n` +
      `  ${location}: estimated layout size ${actual} exceeds ${maximum}. ${guidance}`,
    { path: location },
  );
}

export function assertWrappableContent(value, source, location = "") {
  if (typeof value === "string") {
    const longest = value
      .split(/\s+/u)
      .reduce((maximum, token) => Math.max(maximum, [...token].length), 0);
    if (longest > MAX_UNBROKEN_TEXT_UNITS) {
      throw new WorkbookContentError(
        `Content cannot wrap safely in ${source}:\n` +
          `  ${location || "/"}: contains an unbroken text segment of ${longest} characters; ` +
          `the maximum is ${MAX_UNBROKEN_TEXT_UNITS}. Add normal word breaks or punctuation.`,
        { path: location },
      );
    }
    return;
  }

  if (Array.isArray(value)) {
    value.forEach((item, index) =>
      assertWrappableContent(item, source, `${location}/${index}`),
    );
    return;
  }

  if (value && typeof value === "object") {
    for (const [key, item] of Object.entries(value)) {
      if (key !== "$schema") {
        assertWrappableContent(item, source, `${location}/${key}`);
      }
    }
  }
}

function firstPageLineCount(responseSpace) {
  if (responseSpace.mode === "custom-lines") {
    return Math.min(responseSpace.lines, 14);
  }
  return MINIMUM_FIRST_PAGE_LINE_COUNTS[responseSpace.mode];
}

function assertQuestionLayout(question, source, location) {
  const firstLines = firstPageLineCount(question.responseSpace);
  const maximum = 1800 - firstLines * RESPONSE_LINE_LAYOUT_UNITS;
  const actual =
    layoutUnits(question.prompt) +
    layoutUnits(question.quotation) +
    (question.responseGuidance ?? []).reduce(
      (sum, item) => sum + layoutUnits(item) + 20,
      0,
    );

  assertLayoutBudget(
    source,
    location,
    actual,
    maximum,
    "Shorten the prompt or quotation, reduce the guidance list, or choose fewer first-page response lines.",
  );
}

/**
 * Refuse a lesson that cannot fit the standardized layout.
 *
 * Expects a normalized lesson, because the budgets depend on the response space
 * each question ended up with.
 */
export function assertLessonLayout(lesson, source) {
  const coverUnits =
    layoutUnits(lesson.title) +
    layoutUnits(lesson.readingRange) +
    layoutUnits(lesson.framingNote) +
    layoutUnits(lesson.studentInstructions);
  assertLayoutBudget(
    source,
    "/lesson-cover",
    coverUnits,
    MAX_LESSON_COVER_UNITS,
    "Shorten the lesson title, framing note, or student instructions.",
  );

  for (const [sectionName, items] of [
    ["readingComprehension", lesson.sections.readingComprehension],
    ["criticalThinkingAndAnalysis", lesson.sections.criticalThinkingAndAnalysis],
    ["paragraphWriting", lesson.sections.paragraphWriting],
  ]) {
    items.forEach((item, index) => {
      assertQuestionLayout(item, source, `/sections/${sectionName}/${index}`);
    });
  }

  lesson.sections.vocabulary.forEach((item, index) => {
    const actual =
      layoutUnits(item.term) * 1.5 +
      layoutUnits(item.koreanMeaning) +
      layoutUnits(item.definition) +
      layoutUnits(item.bookExcerpt) +
      layoutUnits(item.excerptContext) +
      layoutUnits(item.chapterReference);
    assertLayoutBudget(
      source,
      `/sections/vocabulary/${index}`,
      actual,
      MAX_VOCABULARY_ENTRY_UNITS,
      "Keep every field intact, but reduce the entry to the curriculum content needed on one reference page.",
    );
  });
}

/** Refuse a teacher edition that has nowhere to put an answer. */
export function assertTeacherGuidance(lesson, source) {
  for (const [sectionName, items] of [
    ["readingComprehension", lesson.sections.readingComprehension],
    ["criticalThinkingAndAnalysis", lesson.sections.criticalThinkingAndAnalysis],
  ]) {
    items.forEach((item, index) => {
      if (typeof item.teacherGuidance === "string" && item.teacherGuidance.trim()) {
        return;
      }

      throw new WorkbookContentError(
        `Teacher guidance is required when teacher PDFs are requested in ${source}:\n` +
          `  /sections/${sectionName}/${index}/teacherGuidance: add answer guidance or export student PDFs only.`,
        { path: `/sections/${sectionName}/${index}/teacherGuidance` },
      );
    });
  }
}

export function defaultResponseSpaceFor(sectionName) {
  const responseSpace = DEFAULT_RESPONSE_SPACES[sectionName];
  if (!responseSpace) {
    throw new WorkbookContentError(
      `Unknown workbook section for response-space default: ${sectionName}`,
    );
  }

  return { ...responseSpace };
}
