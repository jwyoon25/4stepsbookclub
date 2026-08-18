#!/usr/bin/env node

import { resolve } from "node:path";

import {
  buildWorkbookPdfs,
  isExpectedBuildError,
} from "../lib/build.mjs";

const defaultManifest = "workbooks/schema/examples/example-book/workbook.json";
const argumentsAfterCommand = process.argv.slice(2);

if (argumentsAfterCommand.includes("--help") || argumentsAfterCommand.includes("-h")) {
  console.log(
    "Usage: npm run workbook:render -- [path/to/workbook.json] [--output-dir path]",
  );
  console.log(`Default manifest: ${defaultManifest}`);
  process.exit(0);
}

let manifestPath = defaultManifest;
let outputDirectory;

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
  } else if (manifestPath === defaultManifest) {
    manifestPath = argument;
  } else {
    console.error(`Unexpected argument: ${argument}`);
    process.exit(2);
  }
}

try {
  const targets = await buildWorkbookPdfs(resolve(manifestPath), {
    outputDirectory,
  });

  for (const target of targets) {
    console.log(`Created ${target.outputPath}`);
  }
} catch (error) {
  if (isExpectedBuildError(error)) {
    console.error(error.message);
    process.exitCode = 1;
  } else {
    throw error;
  }
}
