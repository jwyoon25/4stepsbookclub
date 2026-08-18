#!/usr/bin/env node

import { resolve } from "node:path";

import {
  loadWorkbookPackage,
  WorkbookContentError,
} from "../lib/content.mjs";

const defaultManifest = "workbooks/schema/examples/example-book/workbook.json";
const argumentsAfterCommand = process.argv.slice(2);

if (argumentsAfterCommand.includes("--help") || argumentsAfterCommand.includes("-h")) {
  console.log("Usage: npm run workbook:validate -- [path/to/workbook.json]");
  console.log(`Default: ${defaultManifest}`);
  process.exit(0);
}

if (argumentsAfterCommand.length > 1) {
  console.error("Expected at most one workbook manifest path.");
  process.exit(2);
}

const manifestPath = resolve(argumentsAfterCommand[0] ?? defaultManifest);

try {
  const workbook = await loadWorkbookPackage(manifestPath);
  const lessonNumbers = workbook.lessons
    .map(({ content }) => content.lessonNumber)
    .join(", ");
  const lessonLabel = workbook.lessons.length === 1 ? "lesson" : "lessons";

  console.log(
    `Valid workbook "${workbook.manifest.bookTitle}" (${workbook.manifest.id}): ` +
      `${workbook.lessons.length} ${lessonLabel}`,
  );
  console.log(`Lesson order: ${lessonNumbers}`);
} catch (error) {
  if (error instanceof WorkbookContentError) {
    console.error(error.message);
    process.exitCode = 1;
  } else {
    throw error;
  }
}

