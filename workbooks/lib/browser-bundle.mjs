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
      bundle: {
        schemaVersion: 1,
        build: { scope, edition },
        manifest,
        lessons,
      },
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

  return { bundleDirectory, buildInfo, fixtures, files };
}
