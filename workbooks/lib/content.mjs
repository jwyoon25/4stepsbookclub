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
    prompt.responseSpace ??= {
      ...DEFAULT_RESPONSE_SPACES.paragraphWriting,
    };
  }

  return normalized;
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

    const previousSource = lessonNumberSources.get(lesson.lessonNumber);
    if (previousSource) {
      throw new WorkbookContentError(
        `Duplicate lesson number ${lesson.lessonNumber}: ${previousSource} and ${lessonFile}`,
      );
    }
    lessonNumberSources.set(lesson.lessonNumber, lessonFile);

    lessons.push({
      file: lessonFile,
      path: realLessonPath,
      content: normalizeLesson(lesson),
    });
  }

  return {
    manifestPath: absoluteManifestPath,
    directory: realManifestDirectory,
    manifest: structuredClone(manifest),
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

