// ---------------------------------------------------------------------------
// The static bundle the browser compiler is loaded from.
//
// The Phase 0 gate in BUILDER-ARCHITECTURE-DECISION.md needs the compiler, the
// workbook templates, the four brand fonts, and the logo assets to arrive in a
// browser as ordinary static files. This module assembles exactly that tree and
// generates the representative build bundles the gate compiles, so the preview
// page, the local gate server, and the verification harness all describe the
// same workbook.
// ---------------------------------------------------------------------------

import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

import Ajv2020 from "ajv/dist/2020.js";
import standaloneCode from "ajv/dist/standalone/index.js";
import addFormats from "ajv-formats";

import { createBuildBundle } from "../builder/browser/build-targets.mjs";
import { PROJECT_FILES } from "../builder/browser/workbook-compiler.mjs";
import { loadWorkbookPackage } from "./content.mjs";

const moduleDirectory = dirname(fileURLToPath(import.meta.url));
const workbooksRoot = resolve(moduleDirectory, "..");
const repositoryRoot = resolve(workbooksRoot, "..");
const browserSourceDirectory = resolve(workbooksRoot, "builder/browser");
const defaultManifestPath = resolve(
  workbooksRoot,
  "schema/examples/example-book/workbook.json",
);
const defaultBundleDirectory = resolve(workbooksRoot, "output/browser-bundle");
const schemaDirectory = resolve(workbooksRoot, "schema");
const SCHEMA_VALIDATORS_PATH = "schema-validators.mjs";

// Cloudflare Pages refuses any single file above 25 MiB, and `engine.core.wasm`
// is 21.7 of them. That is headroom a compiler release could spend without
// anyone noticing until a deploy failed, so the bundle refuses to be built
// rather than refusing to be published.
const MAXIMUM_HOSTED_FILE_BYTES = 25 * 1024 * 1024;

// A representative complete workbook is a full book, not the smoke-test lesson:
// CONTENT-WORKFLOW-DECISIONS.md describes a lesson range such as `Lessons 1–12`,
// and the largest PDF the Drive transfer has to carry is that book's student
// edition.
const REPRESENTATIVE_LESSON_COUNT = 12;

export class BrowserBundleError extends Error {
  constructor(message, options) {
    super(message, options);
    this.name = "BrowserBundleError";
  }
}

export function browserBundleDefaults() {
  return {
    manifestPath: defaultManifestPath,
    outputDirectory: defaultBundleDirectory,
    lessonCount: REPRESENTATIVE_LESSON_COUNT,
  };
}

/**
 * Repeat a package's lessons until the workbook is book-sized.
 *
 * A content package checked into the repository may hold one or two lessons.
 * The gate still has to compile something the size of a real book, so shorter
 * packages are extended by repeating their own validated lessons under new
 * numbers. Nothing about a lesson's shape changes, so the extended workbook
 * stays schema-valid and inside the same layout budgets.
 */
function representativeLessons(lessons, lessonCount) {
  if (lessons.length >= lessonCount) {
    return { lessons: lessons.map(({ content }) => content), extended: false };
  }

  return {
    lessons: Array.from({ length: lessonCount }, (_, index) => {
      const source = lessons[index % lessons.length].content;
      return { ...structuredClone(source), lessonNumber: index + 1 };
    }),
    extended: true,
  };
}

/**
 * Build the normalized bundles the gate compiles.
 *
 * These are the same `schemaVersion: 1` build bundles `lib/build.mjs` writes for
 * the native renderer, so the browser compiles the identical input rather than a
 * preview-only approximation of it.
 */
export async function createFixtureBundles(
  manifestPath = defaultManifestPath,
  { lessonCount = REPRESENTATIVE_LESSON_COUNT } = {},
) {
  const workbook = await loadWorkbookPackage(manifestPath);
  if (workbook.lessons.length === 0) {
    throw new BrowserBundleError(
      `The workbook package contains no lessons: ${manifestPath}`,
    );
  }

  const [firstLesson] = workbook.lessons;
  const complete = representativeLessons(workbook.lessons, lessonCount);
  // Only an extended workbook needs its cover line rewritten. Everything else
  // keeps the manifest the native builder would use, so the browser compiles
  // exactly the bundle `lib/build.mjs` would have handed to the Typst CLI.
  const completeManifest = complete.extended
    ? {
        ...workbook.manifest,
        lessonRange: `Lessons 1–${complete.lessons.length}`,
      }
    : workbook.manifest;

  const scopes = [
    {
      scope: "lesson",
      label: `Standalone lesson ${firstLesson.content.lessonNumber}`,
      lessons: [firstLesson.content],
      manifest: workbook.manifest,
    },
    {
      scope: "workbook",
      label: `Complete workbook (${complete.lessons.length} lessons)`,
      lessons: complete.lessons,
      manifest: completeManifest,
    },
  ];

  return scopes.flatMap(({ scope, label, lessons, manifest }) =>
    ["student", "teacher"].map((edition) => ({
      id: `${scope}-${edition}`,
      label: `${label} · ${edition}`,
      scope,
      edition,
      lessonCount: lessons.length,
      bundle: createBuildBundle(manifest, lessons, { scope, edition }),
    })),
  );
}

function resolvePackageFile(specifier) {
  return fileURLToPath(import.meta.resolve(specifier));
}

// Neither vendored package exports its own `package.json`, so the package root
// is reached through the entry point both of them publish under `dist/`.
function packageDirectory(specifier) {
  return resolve(dirname(resolvePackageFile(specifier)), "..");
}

// typst-wasm ships browser-ready ES modules; only its `nanotar` import needs a
// resolvable URL, which the preview page supplies through an import map.
const VENDOR_FILES = Object.freeze([
  ["typst-wasm", "index.js", "vendor/typst-wasm/index.js"],
  ["typst-wasm/worker/browser", null, "vendor/typst-wasm/worker/browser.js"],
  [
    "typst-wasm/worker/web-worker",
    null,
    "vendor/typst-wasm/worker/web-worker.js",
  ],
  [
    "typst-wasm/engine/engine.core.wasm",
    null,
    "vendor/typst-wasm/engine/engine.core.wasm",
  ],
  [
    "typst-wasm/engine/engine.core2.wasm",
    null,
    "vendor/typst-wasm/engine/engine.core2.wasm",
  ],
  [
    "typst-wasm/engine/engine.core3.wasm",
    null,
    "vendor/typst-wasm/engine/engine.core3.wasm",
  ],
  ["nanotar", null, "vendor/nanotar/index.mjs"],
]);

const VENDOR_LICENSES = Object.freeze([
  ["typst-wasm", "LICENSE", "vendor/typst-wasm/LICENSE"],
  ["nanotar", "LICENSE", "vendor/nanotar/LICENSE"],
]);

const PAGE_FILES = Object.freeze([
  "preview.html",
  "preview.mjs",
  "preview.css",
  "workbook-compiler.mjs",
  // The shared contract the preview runs over live Sheet values. These are the
  // same modules Node imports, copied rather than rewritten, which is what keeps
  // a browser preview and a disk build describing one workbook.
  "sheet-contract.mjs",
  "content-rules.mjs",
  "build-targets.mjs",
  "pdf-archive.mjs",
]);

// The cross-origin-isolated copy of the preview page. Isolation buys the worker
// backend in browsers without JSPI, and costs the `window.opener` channel the
// Apps Script dialog answers on, so the gate needs both variants side by side to
// find out which one the real environment supports.
const ISOLATED_PAGE_PATH = "isolated/preview.html";

// The compiler engine and the brand assets are the expensive part of a cold
// start and only change when a version or the brand changes, so they are cached
// hard. Templates, workbook content, and the page itself are revalidated, so a
// rebuilt bundle is never served from a stale cache.
//
// The patterns do not overlap, deliberately: a static host applies every rule
// that matches and lets the last one win, while the gate server takes the first
// match, and a rule that matched twice would mean two different answers.
export const BUNDLE_CACHE_RULES = Object.freeze([
  ["/vendor/*", "public, max-age=31536000, immutable"],
  ["/project/assets/*", "public, max-age=31536000, immutable"],
  ["/project/system/*", "no-cache"],
  ["/project/src/*", "no-cache"],
  ["/fixtures/*", "no-cache"],
]);

function headersFile() {
  return [
    "# Generated by workbooks/scripts/build-browser-bundle.mjs.",
    "# Cloudflare Pages header syntax; the local gate server applies the same rules.",
    "",
    "/isolated/*",
    "  Cross-Origin-Opener-Policy: same-origin",
    "  Cross-Origin-Embedder-Policy: require-corp",
    "",
    ...BUNDLE_CACHE_RULES.flatMap(([pattern, value]) => [
      pattern,
      `  Cache-Control: ${value}`,
      "",
    ]),
  ].join("\n");
}

/**
 * Turn the JSON schemas into a validator the browser can run.
 *
 * The schemas hold the limits the Sheet contract does not — how long a prompt
 * may be, how many guidance lines an item may carry — and the browser is the
 * export path now, so it has to apply them. Ajv itself is a Node library, but
 * it can generate the validating code ahead of time, which is what this does:
 * the schemas stay the only description of the rules, and what ships is a plain
 * module with no library behind it.
 *
 * Ajv's generated code reaches for one helper, a UTF-16-aware string length.
 * The published copy is CommonJS, so the module carries its own — fifteen lines
 * that a browser can load, rather than a bundler to load fifteen lines.
 */
function replaceUcs2LengthRequire(generated) {
  const required = /require\("ajv\/dist\/runtime\/ucs2length"\)\.default/gu;
  const replaced = generated.replace(required, "ucs2length");
  const remaining = replaced.match(/require\((["'`])(.*?)\1\)/u);
  if (remaining) {
    throw new BrowserBundleError(
      `The generated schema validator needs ${remaining[2]}, which no browser ` +
        "can load. Inline it the way ucs2length is inlined, or the bundle will " +
        "fail only once someone opens it.",
    );
  }
  return replaced;
}

export async function generateSchemaValidators() {
  const [workbookSchema, lessonSchema] = await Promise.all(
    ["workbook.schema.json", "lesson.schema.json"].map(async (name) =>
      JSON.parse(await readFile(resolve(schemaDirectory, name), "utf8")),
    ),
  );

  // The same options `lib/content.mjs` compiles with, so a disk build and a
  // browser export cannot disagree about what the schemas mean.
  const ajv = new Ajv2020({
    allErrors: true,
    strict: true,
    code: { source: true, esm: true },
  });
  addFormats(ajv);
  ajv.addSchema(workbookSchema, "workbook");
  ajv.addSchema(lessonSchema, "lesson");

  const generated = standaloneCode(ajv, {
    validateWorkbook: "workbook",
    validateLesson: "lesson",
  });

  return [
    "// Generated from workbooks/schema/*.json by lib/browser-bundle.mjs.",
    "// Edit the schemas, not this file.",
    "function ucs2length(str) {",
    "  const len = str.length;",
    "  let length = 0;",
    "  let pos = 0;",
    "  while (pos < len) {",
    "    length += 1;",
    "    const value = str.charCodeAt(pos);",
    "    pos += 1;",
    "    if (value >= 0xd800 && value <= 0xdbff && pos < len) {",
    "      const next = str.charCodeAt(pos);",
    "      if ((next & 0xfc00) === 0xdc00) {",
    "        pos += 1;",
    "      }",
    "    }",
    "  }",
    "  return length;",
    "}",
    "",
    replaceUcs2LengthRequire(generated),
  ].join("\n");
}

async function copyInto(sourcePath, bundleDirectory, bundlePath) {
  const destination = join(bundleDirectory, bundlePath);
  await mkdir(dirname(destination), { recursive: true });
  await cp(sourcePath, destination);
  const bytes = await readFile(destination);
  return {
    path: bundlePath,
    bytes: bytes.byteLength,
    gzippedBytes: gzipSync(bytes, { level: 9 }).byteLength,
  };
}

async function writeInto(bundleDirectory, bundlePath, contents) {
  const destination = join(bundleDirectory, bundlePath);
  await mkdir(dirname(destination), { recursive: true });
  await writeFile(destination, contents);
  const bytes = Buffer.from(contents);
  return {
    path: bundlePath,
    bytes: bytes.byteLength,
    gzippedBytes: gzipSync(bytes, { level: 9 }).byteLength,
  };
}

/**
 * Refuse a bundle a static host would reject.
 *
 * The engine is the only file anywhere near the limit, and nothing in this
 * repository decides how large it is: it arrives with a `typst-wasm` release.
 * Failing here names the file and the version that grew; failing at deploy time
 * names neither.
 */
export function assertHostableFiles(files) {
  const tooLarge = files.filter(({ bytes }) => bytes > MAXIMUM_HOSTED_FILE_BYTES);
  if (tooLarge.length === 0) {
    return;
  }

  throw new BrowserBundleError(
    `A static host will not serve files this large:\n${tooLarge
      .map(
        ({ path, bytes }) =>
          `  ${path}: ${(bytes / 1024 / 1024).toFixed(2)} MiB exceeds the ` +
          `${MAXIMUM_HOSTED_FILE_BYTES / 1024 / 1024} MiB limit`,
      )
      .join("\n")}`,
  );
}

/**
 * Write the deployable static bundle.
 *
 * The result is self-contained: served from the root of any static host, or
 * from the local gate server, it is everything a browser needs to compile a
 * workbook without a render service.
 */
export async function writeBrowserBundle({
  manifestPath = defaultManifestPath,
  outputDirectory = defaultBundleDirectory,
  lessonCount = REPRESENTATIVE_LESSON_COUNT,
  nativeTypstVersion = null,
} = {}) {
  const bundleDirectory = resolve(outputDirectory);
  const fixtures = await createFixtureBundles(manifestPath, { lessonCount });

  await rm(bundleDirectory, { recursive: true, force: true });
  await mkdir(bundleDirectory, { recursive: true });

  const files = [];

  for (const page of PAGE_FILES) {
    files.push(
      await copyInto(resolve(browserSourceDirectory, page), bundleDirectory, page),
    );
  }
  files.push(
    await copyInto(
      resolve(browserSourceDirectory, "preview.html"),
      bundleDirectory,
      ISOLATED_PAGE_PATH,
    ),
  );

  files.push(
    await writeInto(
      bundleDirectory,
      SCHEMA_VALIDATORS_PATH,
      await generateSchemaValidators(),
    ),
  );

  for (const projectFile of PROJECT_FILES) {
    files.push(
      await copyInto(
        resolve(workbooksRoot, projectFile),
        bundleDirectory,
        `project/${projectFile}`,
      ),
    );
  }

  for (const [specifier, relativeFile, bundlePath] of VENDOR_FILES) {
    const resolved = resolvePackageFile(specifier);
    const sourcePath = relativeFile
      ? resolve(dirname(resolved), relativeFile)
      : resolved;
    files.push(await copyInto(sourcePath, bundleDirectory, bundlePath));
  }

  for (const [specifier, relativeFile, bundlePath] of VENDOR_LICENSES) {
    files.push(
      await copyInto(
        resolve(packageDirectory(specifier), relativeFile),
        bundleDirectory,
        bundlePath,
      ),
    );
  }

  const fixtureIndex = fixtures.map(
    ({ id, label, scope, edition, lessonCount: lessons }) => ({
      id,
      label,
      scope,
      edition,
      lessonCount: lessons,
    }),
  );
  files.push(
    await writeInto(
      bundleDirectory,
      "fixtures/index.json",
      `${JSON.stringify(fixtureIndex, null, 2)}\n`,
    ),
  );
  for (const fixture of fixtures) {
    files.push(
      await writeInto(
        bundleDirectory,
        `fixtures/${fixture.id}.json`,
        `${JSON.stringify(fixture.bundle, null, 2)}\n`,
      ),
    );
  }

  const typstWasmVersion = JSON.parse(
    await readFile(join(packageDirectory("typst-wasm"), "package.json"), "utf8"),
  ).version;
  const buildInfo = {
    generatedAt: new Date().toISOString(),
    workbookId: fixtures[0].bundle.manifest.id,
    bookTitle: fixtures[0].bundle.manifest.bookTitle,
    manifestPath: relative(repositoryRoot, manifestPath),
    typstWasmVersion,
    nativeTypstVersion,
    projectFiles: PROJECT_FILES.length,
    fixtures: fixtureIndex,
  };
  files.push(
    await writeInto(
      bundleDirectory,
      "build-info.json",
      `${JSON.stringify(buildInfo, null, 2)}\n`,
    ),
  );
  files.push(await writeInto(bundleDirectory, "_headers", headersFile()));

  assertHostableFiles(files);

  return { bundleDirectory, buildInfo, fixtures, files };
}
