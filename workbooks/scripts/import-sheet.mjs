#!/usr/bin/env node

import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { buildWorkbookPdfs, isExpectedBuildError } from "../lib/build.mjs";
import {
  readWorkbookSheet,
  WorkbookSheetError,
  writeWorkbookPackage,
} from "../lib/sheet-import.mjs";

const args = process.argv.slice(2);

if (args.includes("--help") || args.includes("-h")) {
  console.log(
    "Usage: npm run workbook:import-sheet -- path/to/workbook.xlsx [--id workbook-id] [--output-dir path] [--render] [--pdf-output-dir path]",
  );
  process.exit(0);
}

let inputPath;
let workbookId;
let outputDirectory;
let pdfOutputDirectory;
let shouldRender = false;

function optionValue(name, index) {
  const value = args[index + 1];
  if (!value || value.startsWith("--")) {
    throw new WorkbookSheetError(`${name} requires a value.`);
  }
  return value;
}

try {
  for (let index = 0; index < args.length; index += 1) {
    const argument = args[index];
    if (argument === "--id") {
      workbookId = optionValue(argument, index);
      index += 1;
    } else if (argument === "--output-dir") {
      outputDirectory = resolve(optionValue(argument, index));
      index += 1;
    } else if (argument === "--render") {
      shouldRender = true;
    } else if (argument === "--pdf-output-dir") {
      pdfOutputDirectory = resolve(optionValue(argument, index));
      index += 1;
    } else if (argument.startsWith("--")) {
      throw new WorkbookSheetError(`Unknown option: ${argument}`);
    } else if (!inputPath) {
      inputPath = resolve(argument);
    } else {
      throw new WorkbookSheetError(`Unexpected argument: ${argument}`);
    }
  }

  if (!inputPath) {
    throw new WorkbookSheetError(
      "An .xlsx file is required. Run with --help for usage.",
    );
  }
  if (pdfOutputDirectory && !shouldRender) {
    throw new WorkbookSheetError("--pdf-output-dir requires --render.");
  }

  if (outputDirectory && !workbookId) {
    try {
      const existingManifest = JSON.parse(
        await readFile(resolve(outputDirectory, "workbook.json"), "utf8"),
      );
      if (typeof existingManifest.id === "string") {
        workbookId = existingManifest.id;
      }
    } catch (error) {
      if (error?.code !== "ENOENT") {
        throw new WorkbookSheetError(
          `Could not reuse the workbook ID from ${resolve(outputDirectory, "workbook.json")}.`,
          { cause: error },
        );
      }
    }
  }

  const sheetPackage = await readWorkbookSheet(inputPath, { workbookId });
  outputDirectory ??= resolve(
    "workbooks/content",
    sheetPackage.manifest.id,
  );
  const result = await writeWorkbookPackage(sheetPackage, outputDirectory);
  console.log(
    `Imported ${result.lessonCount} lesson${result.lessonCount === 1 ? "" : "s"} to ${result.manifestPath}`,
  );

  if (shouldRender) {
    const targets = await buildWorkbookPdfs(result.manifestPath, {
      outputDirectory: pdfOutputDirectory,
    });
    for (const target of targets) {
      console.log(`Created ${target.outputPath}`);
    }
  }
} catch (error) {
  if (error instanceof WorkbookSheetError || isExpectedBuildError(error)) {
    console.error(error.message);
    process.exitCode = 1;
  } else {
    throw error;
  }
}
