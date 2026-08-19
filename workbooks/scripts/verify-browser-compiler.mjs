#!/usr/bin/env node

// ---------------------------------------------------------------------------
// Prove the browser compiler agrees with the native renderer.
//
// For every representative workbook this compiles the same bundle twice — once
// with the WebAssembly compiler the preview page uses, once with the Typst CLI
// the production build uses — then audits the WebAssembly output with the
// existing workbook audit and compares the two renderings, first by every text
// run and response rule, then pixel by pixel.
//
// This is the local half of Phase 0. It cannot answer what a Google Apps Script
// dialog allows; it answers everything else, and it answers it repeatably.
// ---------------------------------------------------------------------------

import { resolve } from "node:path";

import { WorkbookCompilerError } from "../builder/browser/workbook-compiler.mjs";
import {
  browserBundleDefaults,
  createFixtureBundles,
} from "../lib/browser-bundle.mjs";
import {
  DEFAULT_COMPARISON_PPI,
  verifyWorkbookFixture,
  withVerificationDirectory,
} from "../lib/browser-verification.mjs";
import { WorkbookBuildError } from "../lib/build.mjs";
import { WorkbookContentError } from "../lib/content.mjs";
import {
  createWorkbookTypstCompiler,
  TypstCompilerError,
} from "../lib/typst-compiler.mjs";

const defaults = browserBundleDefaults();
const defaultManifest = "workbooks/schema/examples/example-book/workbook.json";
const argumentsAfterCommand = process.argv.slice(2);

if (argumentsAfterCommand.includes("--help") || argumentsAfterCommand.includes("-h")) {
  console.log(
    "Usage: npm run workbook:browser-verify -- [path/to/workbook.json] " +
      "[--lessons count] [--only id,id] [--no-pixels] [--ppi number]",
  );
  console.log(`Default manifest: ${defaultManifest}`);
  console.log(`Default lessons:  ${defaults.lessonCount} in the complete workbook`);
  process.exit(0);
}

let manifestArgument;
let lessonCount = defaults.lessonCount;
let only = null;
let comparePixels = true;
let ppi = DEFAULT_COMPARISON_PPI;

for (let index = 0; index < argumentsAfterCommand.length; index += 1) {
  const argument = argumentsAfterCommand[index];
  if (argument === "--lessons") {
    const value = Number(argumentsAfterCommand[index + 1]);
    if (!Number.isInteger(value) || value < 1) {
      console.error("--lessons requires a whole number of lessons.");
      process.exit(2);
    }
    lessonCount = value;
    index += 1;
  } else if (argument === "--only") {
    const value = argumentsAfterCommand[index + 1];
    if (!value) {
      console.error("--only requires one or more workbook ids.");
      process.exit(2);
    }
    only = value.split(",").map((id) => id.trim());
    index += 1;
  } else if (argument === "--no-pixels") {
    comparePixels = false;
  } else if (argument === "--ppi") {
    const value = Number(argumentsAfterCommand[index + 1]);
    if (!Number.isInteger(value) || value < 1) {
      console.error("--ppi requires a whole number.");
      process.exit(2);
    }
    ppi = value;
    index += 1;
  } else if (manifestArgument === undefined) {
    manifestArgument = argument;
  } else {
    console.error(`Unexpected argument: ${argument}`);
    process.exit(2);
  }
}

function milliseconds(value) {
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${Math.round(value)} ms`;
}

function count(value) {
  return value.toLocaleString("en-US");
}

function describe(result) {
  const lines = [
    [
      "compile",
      `browser ${milliseconds(result.browserMilliseconds)} · ` +
        `native ${milliseconds(result.nativeMilliseconds)} · ` +
        `${(result.browserBytes / 1024).toFixed(0)} KB`,
    ],
    ["engines", `${result.engines.browser} · ${result.engines.native}`],
    // The browser compilation refuses any diagnostic, so reaching this line is
    // itself the result: the workbook compiled cleanly.
    ["diagnostics", "none"],
    [
      "audit",
      result.audit.passed
        ? `passed · ${result.audit.pageCount} pages`
        : `FAILED · ${result.audit.error}`,
    ],
    [
      "text parity",
      result.text.identical
        ? `identical · ${count(result.text.textItems)} runs · ` +
          `${count(result.text.ruledLines)} rules · ` +
          `worst offset ${result.text.worstOffsetPoints.toFixed(3)} pt`
        : `DIFFERENT · ${result.text.summary}`,
    ],
  ];

  if (result.pixels) {
    lines.push([
      "pixel parity",
      result.pixels.identical
        ? `identical · ${count(result.pixels.totalChannels)} channels at ` +
          `${result.pixels.ppi} ppi`
        : `DIFFERENT · ${result.pixels.summary}`,
    ]);
  }

  return lines;
}

try {
  const fixtures = (
    await createFixtureBundles(resolve(manifestArgument ?? defaultManifest), {
      lessonCount,
    })
  ).filter((fixture) => only === null || only.includes(fixture.id));

  if (fixtures.length === 0) {
    console.error(`No workbook matched --only ${only.join(",")}`);
    process.exit(2);
  }

  const { compiler, backend, readyMilliseconds, projectMilliseconds, projectBytes } =
    await createWorkbookTypstCompiler();
  console.log(
    `Compiler ready on the ${backend} backend in ${milliseconds(readyMilliseconds)}; ` +
      `templates, fonts, and logos (${(projectBytes / 1024 / 1024).toFixed(2)} MB) ` +
      `loaded in ${milliseconds(projectMilliseconds)}.`,
  );

  const failures = await withVerificationDirectory(async (directory) => {
    let failed = 0;
    try {
      for (const fixture of fixtures) {
        const result = await verifyWorkbookFixture(compiler, fixture, {
          directory,
          ppi,
          comparePixels,
        });

        console.log("");
        console.log(`${fixture.label} · ${result.pageCount} pages`);
        for (const [label, detail] of describe(result)) {
          console.log(`  ${label.padEnd(13)} ${detail}`);
        }
        if (!result.passed) {
          failed += 1;
        }
      }
    } finally {
      await compiler.dispose();
    }
    return failed;
  });

  console.log("");
  if (failures === 0) {
    console.log(
      `${fixtures.length} ${fixtures.length === 1 ? "workbook" : "workbooks"} ` +
        "compiled in the browser compiler, audited, and identical to the native " +
        "renderer.",
    );
  } else {
    console.error(
      `${failures} of ${fixtures.length} workbooks did not match the native renderer.`,
    );
    process.exitCode = 1;
  }
} catch (error) {
  if (
    error instanceof WorkbookCompilerError ||
    error instanceof WorkbookBuildError ||
    error instanceof WorkbookContentError ||
    error instanceof TypstCompilerError
  ) {
    console.error(error.message);
    process.exitCode = 1;
  } else {
    throw error;
  }
}
