#!/usr/bin/env node

import { resolve } from "node:path";

import {
  loadWorkbookPackage,
  WorkbookContentError,
} from "../lib/content.mjs";

const defaultManifest = "workbooks/schema/examples/example-book/workbook.json";
const argumentsAfterCommand = process.argv.slice(2);

if (argumentsAfterCommand.includes("--help") || argumentsAfterCommand.includes("-h")) {
  console.log(
    "Usage: npm run workbook:validate -- [path/to/workbook.json] [--editions student|teacher|both]",
  );
  console.log(`Default: ${defaultManifest}`);
  process.exit(0);
}

let manifestArgument;
let editions = ["student", "teacher"];

for (let index = 0; index < argumentsAfterCommand.length; index += 1) {
  const argument = argumentsAfterCommand[index];
  if (argument === "--editions") {
    const value = argumentsAfterCommand[index + 1];
    if (!value) {
      console.error("--editions requires student, teacher, or both.");
      process.exit(2);
    }
    if (value === "both") {
      editions = ["student", "teacher"];
    } else if (["student", "teacher"].includes(value)) {
      editions = [value];
    } else {
      console.error("--editions must be student, teacher, or both.");
      process.exit(2);
    }
    index += 1;
  } else if (manifestArgument === undefined) {
    manifestArgument = argument;
  } else {
    console.error(`Unexpected argument: ${argument}`);
    process.exit(2);
  }
}

const manifestPath = resolve(manifestArgument ?? defaultManifest);

try {
  const workbook = await loadWorkbookPackage(manifestPath, {
    requireTeacherGuidance: editions.includes("teacher"),
  });
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
