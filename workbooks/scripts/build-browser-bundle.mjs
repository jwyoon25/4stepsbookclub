#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { relative, resolve } from "node:path";

import {
  BrowserBundleError,
  browserBundleDefaults,
  writeBrowserBundle,
} from "../lib/browser-bundle.mjs";
import { WorkbookContentError } from "../lib/content.mjs";

const defaults = browserBundleDefaults();
const defaultManifest = "workbooks/schema/examples/example-book/workbook.json";
const argumentsAfterCommand = process.argv.slice(2);

if (argumentsAfterCommand.includes("--help") || argumentsAfterCommand.includes("-h")) {
  console.log(
    "Usage: npm run workbook:browser-bundle -- [path/to/workbook.json] " +
      "[--output-dir path] [--lessons count]",
  );
  console.log(`Default manifest: ${defaultManifest}`);
  console.log(`Default output:   ${relative(process.cwd(), defaults.outputDirectory)}`);
  console.log(`Default lessons:  ${defaults.lessonCount} in the complete workbook`);
  process.exit(0);
}

let manifestArgument;
let outputDirectory = defaults.outputDirectory;
let lessonCount = defaults.lessonCount;

for (let index = 0; index < argumentsAfterCommand.length; index += 1) {
  const argument = argumentsAfterCommand[index];
  if (argument === "--output-dir") {
    const value = argumentsAfterCommand[index + 1];
    if (!value) {
      console.error("--output-dir requires a path.");
      process.exit(2);
    }
    outputDirectory = resolve(value);
    index += 1;
  } else if (argument === "--lessons") {
    const value = Number(argumentsAfterCommand[index + 1]);
    if (!Number.isInteger(value) || value < 1) {
      console.error("--lessons requires a whole number of lessons.");
      process.exit(2);
    }
    lessonCount = value;
    index += 1;
  } else if (manifestArgument === undefined) {
    manifestArgument = argument;
  } else {
    console.error(`Unexpected argument: ${argument}`);
    process.exit(2);
  }
}

function nativeTypstVersion() {
  const result = spawnSync("typst", ["--version"], { encoding: "utf8" });
  return result.status === 0 ? result.stdout.trim() : null;
}

function megabytes(bytes) {
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function areaOf(path) {
  if (path.startsWith("vendor/")) {
    return "compiler";
  }
  if (path.startsWith("project/assets/fonts/")) {
    return "fonts";
  }
  if (path.startsWith("project/")) {
    return "templates and logos";
  }
  if (path.startsWith("fixtures/")) {
    return "workbook content";
  }
  return "preview page";
}

try {
  const { bundleDirectory, buildInfo, files } = await writeBrowserBundle({
    manifestPath: resolve(manifestArgument ?? defaultManifest),
    outputDirectory,
    lessonCount,
    nativeTypstVersion: nativeTypstVersion(),
  });

  const areas = new Map();
  for (const file of files) {
    const area = areaOf(file.path);
    const totals = areas.get(area) ?? { bytes: 0, gzippedBytes: 0, files: 0 };
    totals.bytes += file.bytes;
    totals.gzippedBytes += file.gzippedBytes;
    totals.files += 1;
    areas.set(area, totals);
  }

  console.log(`Wrote ${files.length} files to ${relative(process.cwd(), bundleDirectory)}`);
  console.log(
    `Workbook: ${buildInfo.bookTitle} (${buildInfo.workbookId}); ` +
      `typst-wasm ${buildInfo.typstWasmVersion}` +
      (buildInfo.nativeTypstVersion ? `; native ${buildInfo.nativeTypstVersion}` : ""),
  );
  console.log("");
  console.log("A browser downloads this once, then serves it from cache:");
  console.log("");

  let bytes = 0;
  let gzippedBytes = 0;
  for (const [area, totals] of areas) {
    bytes += totals.bytes;
    gzippedBytes += totals.gzippedBytes;
    console.log(
      `  ${area.padEnd(21)} ${megabytes(totals.bytes).padStart(9)}` +
        `  ${megabytes(totals.gzippedBytes).padStart(9)} compressed`,
    );
  }
  console.log(
    `  ${"total".padEnd(21)} ${megabytes(bytes).padStart(9)}` +
      `  ${megabytes(gzippedBytes).padStart(9)} compressed`,
  );
} catch (error) {
  if (error instanceof BrowserBundleError || error instanceof WorkbookContentError) {
    console.error(error.message);
    process.exitCode = 1;
  } else {
    throw error;
  }
}
