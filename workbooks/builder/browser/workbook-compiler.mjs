// ---------------------------------------------------------------------------
// The workbook project, as a browser-side Typst compiler adapter.
//
// This is the single description of which files make up a compilable 4steps
// workbook project. The Node bundle builder imports it to decide what to copy
// into the static bundle, the preview page imports it to load those same files
// into an in-memory compiler, and the verification harness imports it to prove
// the result matches the native renderer. There is no second list to keep in
// step.
//
// Nothing here is specific to typst-wasm's transport: the caller supplies an
// already-created compiler and two readers. That keeps this file usable from a
// browser (fetch), from Node (fs), and from whatever Phase 1 chooses next.
// ---------------------------------------------------------------------------

// Virtual project paths are relative and never begin with a slash: the compiler
// rejects a leading slash as an invalid project path. Typst's own root-absolute
// references inside these sources — `image("/assets/logo/…")` and the `data`
// input below — still resolve, because the virtual project root is the same
// root the native build passes as `--root workbooks`.
export const PROJECT_SOURCE_FILES = Object.freeze([
  "system/tokens.typ",
  "system/components.typ",
  "system/renderer.typ",
  "src/render.typ",
]);

// Every brand logo the design system can address, not only the ones the current
// components happen to use, so switching a token to a dark variant does not
// silently fail in the browser while still working natively.
export const PROJECT_IMAGE_FILES = Object.freeze([
  "assets/logo/logomark-large-light.png",
  "assets/logo/logomark-large-dark.png",
  "assets/logo/logomark-small-light.png",
  "assets/logo/logomark-small-dark.png",
  "assets/logo/logotype-light.png",
  "assets/logo/logotype-dark.png",
]);

// The four vendored brand faces. The native build reaches these through
// `--font-path`; in the browser they have to be registered explicitly, and a
// missing one substitutes silently rather than failing, so all four are loaded
// before anything compiles.
export const PROJECT_FONT_FILES = Object.freeze([
  "assets/fonts/GowunBatang-Regular.ttf",
  "assets/fonts/GowunBatang-Bold.ttf",
  "assets/fonts/IBMPlexSansKR-Regular.ttf",
  "assets/fonts/IBMPlexSansKR-SemiBold.ttf",
]);

export const PROJECT_FILES = Object.freeze([
  ...PROJECT_SOURCE_FILES,
  ...PROJECT_IMAGE_FILES,
  ...PROJECT_FONT_FILES,
]);

export const MAIN_SOURCE_PATH = "src/render.typ";
export const BUILD_BUNDLE_PATH = "build/bundle.json";

export class WorkbookCompilerError extends Error {
  constructor(message, options) {
    super(message, options);
    this.name = "WorkbookCompilerError";
  }
}

function formatDiagnostics(diagnostics) {
  return diagnostics
    .map((diagnostic) => diagnostic.formatted?.trim() || diagnostic.message)
    .join("\n");
}

/**
 * Load the workbook design system, brand assets, and fonts into a compiler.
 *
 * `readText` and `readBytes` receive one of the paths above and return the file
 * contents; `readBytes` must resolve to a `Uint8Array`.
 *
 * Returns the milliseconds spent on each stage, because a usable cold start is
 * one of the things the Phase 0 gate has to measure rather than assume.
 */
export async function loadWorkbookProject(compiler, { readText, readBytes }) {
  const startedAt = Date.now();

  const sources = await Promise.all(PROJECT_SOURCE_FILES.map(readText));
  const images = await Promise.all(PROJECT_IMAGE_FILES.map(readBytes));
  const fonts = await Promise.all(PROJECT_FONT_FILES.map(readBytes));
  const fetchedAt = Date.now();

  for (const [index, path] of PROJECT_SOURCE_FILES.entries()) {
    await compiler.addSource(path, sources[index]);
  }
  for (const [index, path] of PROJECT_IMAGE_FILES.entries()) {
    await compiler.addFile(path, images[index]);
  }
  await compiler.addFonts(...fonts);
  await compiler.setMain(MAIN_SOURCE_PATH);

  return {
    fetchMilliseconds: fetchedAt - startedAt,
    registerMilliseconds: Date.now() - fetchedAt,
    bytes: [...images, ...fonts].reduce((total, file) => total + file.byteLength, 0),
  };
}

async function compileBundle(compiler, bundle, options) {
  const source = new TextEncoder().encode(`${JSON.stringify(bundle, null, 2)}\n`);
  await compiler.addFile(BUILD_BUNDLE_PATH, source);

  let result;
  try {
    result = await compiler.compile({
      ...options,
      inputs: { data: `/${BUILD_BUNDLE_PATH}` },
    });
  } catch (cause) {
    const diagnostics = cause?.diagnostics ?? [];
    throw new WorkbookCompilerError(
      `Typst failed while compiling the workbook${
        diagnostics.length > 0 ? `:\n${formatDiagnostics(diagnostics)}` : "."
      }`,
      { cause },
    );
  }

  // The native build refuses to publish a PDF that compiled with any warning at
  // all. The browser path holds the same line: a warning here means the two
  // renderers no longer agree about what a clean build is.
  const diagnostics = result.diagnostics ?? [];
  if (diagnostics.length > 0) {
    throw new WorkbookCompilerError(
      `Typst reported diagnostics while compiling the workbook:\n${formatDiagnostics(diagnostics)}`,
    );
  }

  return result;
}

/** Compile one normalized build bundle into PDF bytes. */
export async function compileWorkbookPdf(compiler, bundle) {
  const result = await compileBundle(compiler, bundle, { format: "pdf" });
  return result.output;
}

/**
 * Read the Typst version out of a generated PDF.
 *
 * The browser compiler and the installed CLI are versioned separately, so which
 * two engines produced a matching pair of PDFs is part of the record.
 */
export function readPdfCreator(bytes) {
  const decoder = new TextDecoder("latin1");
  const pattern = /\/Creator\s*\(([^)]+)\)/;
  // The document information dictionary is written near the end of the file, so
  // the tail is read first and the whole document only if that misses.
  const tail = decoder.decode(bytes.subarray(Math.max(0, bytes.length - 16384)));
  return (
    tail.match(pattern)?.[1] ?? decoder.decode(bytes).match(pattern)?.[1] ?? "unknown"
  );
}

/**
 * Compile one normalized build bundle into page rasters.
 *
 * Only the parity harness needs this: comparing rendered pixels is how visual
 * parity with the native renderer is proven rather than asserted.
 */
export async function compileWorkbookPages(compiler, bundle, { ppi = 72 } = {}) {
  const result = await compileBundle(compiler, bundle, { format: "png", ppi });
  return result.pages.map(({ page, output }) => ({ page, png: output }));
}
