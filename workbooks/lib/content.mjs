import { readFile, realpath } from "node:fs/promises";
import { dirname, isAbsolute, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const moduleDirectory = dirname(fileURLToPath(import.meta.url));
const schemaDirectory = resolve(moduleDirectory, "../schema");

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

let validatorsPromise;

export class WorkbookContentError extends Error {
  constructor(message, options) {
    super(message, options);
    this.name = "WorkbookContentError";
  }
}

async function readJson(filePath) {
  let source;

  try {
    source = await readFile(filePath, "utf8");
  } catch (cause) {
    if (cause?.code === "ENOENT") {
      throw new WorkbookContentError(`Content file does not exist: ${filePath}`, {
        cause,
      });
    }

    throw new WorkbookContentError(`Could not read content file: ${filePath}`, {
      cause,
    });
  }

  try {
    return JSON.parse(source);
  } catch (cause) {
    throw new WorkbookContentError(`Invalid JSON in ${filePath}: ${cause.message}`, {
      cause,
    });
  }
}

async function createValidators() {
  const [workbookSchema, lessonSchema] = await Promise.all([
    readJson(resolve(schemaDirectory, "workbook.schema.json")),
    readJson(resolve(schemaDirectory, "lesson.schema.json")),
  ]);
  const ajv = new Ajv2020({ allErrors: true, strict: true });
  addFormats(ajv);

  return {
    workbook: ajv.compile(workbookSchema),
    lesson: ajv.compile(lessonSchema),
  };
}

function getValidators() {
  validatorsPromise ??= createValidators();
  return validatorsPromise;
}

function validationLocation(error) {
  let location = error.instancePath || "/";

  if (error.keyword === "required") {
    location = `${location === "/" ? "" : location}/${error.params.missingProperty}`;
  } else if (error.keyword === "additionalProperties") {
    location = `${location === "/" ? "" : location}/${error.params.additionalProperty}`;
  }

  return location || "/";
}

function assertValid(validator, value, filePath) {
  if (validator(value)) {
    return;
  }

  const details = validator.errors
    .map(
      (error) =>
        `  ${validationLocation(error)}: ${error.message ?? "is invalid"}`,
    )
    .join("\n");

  throw new WorkbookContentError(
    `Content does not match the schema in ${filePath}:\n${details}`,
  );
}

function isInside(parentPath, candidatePath) {
  const pathFromParent = relative(parentPath, candidatePath);
  return (
    pathFromParent !== "" &&
    pathFromParent !== ".." &&
    !pathFromParent.startsWith(`..${sep}`) &&
    !isAbsolute(pathFromParent)
  );
}

function normalizeLesson(lesson) {
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

function normalizeManifest(manifest) {
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

function assertLayoutBudget(filePath, location, actual, maximum, guidance) {
  if (actual <= maximum) {
    return;
  }

  throw new WorkbookContentError(
    `Content is too long for the standardized workbook layout in ${filePath}:\n` +
      `  ${location}: estimated layout size ${actual} exceeds ${maximum}. ${guidance}`,
  );
}

function assertWrappableContent(value, filePath, location = "") {
  if (typeof value === "string") {
    const longest = value
      .split(/\s+/u)
      .reduce((maximum, token) => Math.max(maximum, [...token].length), 0);
    if (longest > MAX_UNBROKEN_TEXT_UNITS) {
      throw new WorkbookContentError(
        `Content cannot wrap safely in ${filePath}:\n` +
          `  ${location || "/"}: contains an unbroken text segment of ${longest} characters; ` +
          `the maximum is ${MAX_UNBROKEN_TEXT_UNITS}. Add normal word breaks or punctuation.`,
      );
    }
    return;
  }

  if (Array.isArray(value)) {
    value.forEach((item, index) =>
      assertWrappableContent(item, filePath, `${location}/${index}`),
    );
    return;
  }

  if (value && typeof value === "object") {
    for (const [key, item] of Object.entries(value)) {
      if (key !== "$schema") {
        assertWrappableContent(item, filePath, `${location}/${key}`);
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

function assertQuestionLayout(question, filePath, location) {
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
    filePath,
    location,
    actual,
    maximum,
    "Shorten the prompt or quotation, reduce the guidance list, or choose fewer first-page response lines.",
  );
}

function assertLessonLayout(lesson, filePath) {
  const coverUnits =
    layoutUnits(lesson.title) +
    layoutUnits(lesson.readingRange) +
    layoutUnits(lesson.framingNote) +
    layoutUnits(lesson.studentInstructions);
  assertLayoutBudget(
    filePath,
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
      assertQuestionLayout(
        item,
        filePath,
        `/sections/${sectionName}/${index}`,
      );
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
      filePath,
      `/sections/vocabulary/${index}`,
      actual,
      MAX_VOCABULARY_ENTRY_UNITS,
      "Keep every field intact, but reduce the entry to the curriculum content needed on one reference page.",
    );
  });
}

/**
 * Load, validate, and normalize a complete workbook content package.
 *
 * The returned lesson order is the manifest order. Response-space presets stay
 * semantic; the renderer owns their eventual line/page geometry.
 */
export async function loadWorkbookPackage(manifestPath) {
  const absoluteManifestPath = resolve(manifestPath);
  const manifestDirectory = dirname(absoluteManifestPath);
  const [manifest, validators] = await Promise.all([
    readJson(absoluteManifestPath),
    getValidators(),
  ]);
  assertValid(validators.workbook, manifest, absoluteManifestPath);
  const normalizedManifest = normalizeManifest(manifest);
  assertWrappableContent(normalizedManifest, absoluteManifestPath);

  const realManifestDirectory = await realpath(manifestDirectory);
  const lessons = [];
  const lessonNumberSources = new Map();

  for (const lessonFile of manifest.lessonFiles) {
    const lessonPath = resolve(manifestDirectory, lessonFile);

    if (!isInside(manifestDirectory, lessonPath)) {
      throw new WorkbookContentError(
        `Lesson path leaves the workbook directory: ${lessonFile}`,
      );
    }

    let realLessonPath;
    try {
      realLessonPath = await realpath(lessonPath);
    } catch (cause) {
      if (cause?.code === "ENOENT") {
        throw new WorkbookContentError(
          `Lesson file does not exist: ${lessonFile}`,
          { cause },
        );
      }

      throw new WorkbookContentError(`Could not resolve lesson file: ${lessonFile}`, {
        cause,
      });
    }

    if (!isInside(realManifestDirectory, realLessonPath)) {
      throw new WorkbookContentError(
        `Lesson path resolves outside the workbook directory: ${lessonFile}`,
      );
    }

    const lesson = await readJson(realLessonPath);
    assertValid(validators.lesson, lesson, realLessonPath);
    assertWrappableContent(lesson, realLessonPath);

    const previousSource = lessonNumberSources.get(lesson.lessonNumber);
    if (previousSource) {
      throw new WorkbookContentError(
        `Duplicate lesson number ${lesson.lessonNumber}: ${previousSource} and ${lessonFile}`,
      );
    }
    lessonNumberSources.set(lesson.lessonNumber, lessonFile);

    const normalizedLesson = normalizeLesson(lesson);
    assertLessonLayout(normalizedLesson, realLessonPath);

    lessons.push({
      file: lessonFile,
      path: realLessonPath,
      content: normalizedLesson,
    });
  }

  return {
    manifestPath: absoluteManifestPath,
    directory: realManifestDirectory,
    manifest: normalizedManifest,
    lessons,
  };
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
