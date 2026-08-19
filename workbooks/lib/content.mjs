// ---------------------------------------------------------------------------
// Loading a workbook content package from disk.
//
// The rules about what content means — the response-space defaults, the layout
// budgets, the wrapping limit, the teacher-guidance requirement — live in
// `builder/browser/content-rules.mjs` so the browser preview applies exactly the
// same ones. What is here is the part that needs a filesystem and the JSON
// schemas: reading the manifest and its lessons, keeping them inside the
// package directory, and validating their shape.
// ---------------------------------------------------------------------------

import { readFile, realpath } from "node:fs/promises";
import { dirname, isAbsolute, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

import {
  assertLessonLayout,
  assertTeacherGuidance,
  assertWrappableContent,
  normalizeLesson,
  normalizeManifest,
  WorkbookContentError,
} from "../builder/browser/content-rules.mjs";

export {
  defaultResponseSpaceFor,
  WorkbookContentError,
} from "../builder/browser/content-rules.mjs";

const moduleDirectory = dirname(fileURLToPath(import.meta.url));
const schemaDirectory = resolve(moduleDirectory, "../schema");

let validatorsPromise;

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

/**
 * Load, validate, and normalize a complete workbook content package.
 *
 * The returned lesson order is the manifest order. Response-space presets stay
 * semantic; the renderer owns their eventual line/page geometry.
 */
export async function loadWorkbookPackage(
  manifestPath,
  { requireTeacherGuidance = true } = {},
) {
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
    if (requireTeacherGuidance) {
      assertTeacherGuidance(lesson, realLessonPath);
    }

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
