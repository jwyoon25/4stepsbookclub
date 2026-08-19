// ---------------------------------------------------------------------------
// One workbook, compiled twice and compared.
//
// Both the command-line harness and the test suite ask the same question of the
// browser compiler: does it produce a workbook that passes the existing audit
// and is indistinguishable from the native renderer's? The answer is assembled
// here so the two callers cannot check subtly different things.
// ---------------------------------------------------------------------------

import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  compileWorkbookPages,
  compileWorkbookPdf,
  readPdfCreator,
} from "../builder/browser/workbook-compiler.mjs";
import { compileBundleWithNativeTypst } from "./build.mjs";
import { auditWorkbookPdf, WorkbookPdfAuditError } from "./pdf-audit.mjs";
import { comparePagePixels, comparePdfDocuments } from "./render-parity.mjs";

const moduleDirectory = dirname(fileURLToPath(import.meta.url));
const workbooksRoot = resolve(moduleDirectory, "..");
const temporaryParent = resolve(workbooksRoot, "output/.build");

export const DEFAULT_COMPARISON_PPI = 72;

/**
 * Run something in a scratch directory the native compiler can reach.
 *
 * Typst is given the workbook root and cannot read outside it, so a comparison
 * cannot use the system temporary directory.
 */
export async function withVerificationDirectory(run) {
  await mkdir(temporaryParent, { recursive: true });
  const directory = await mkdtemp(join(temporaryParent, "verify-"));
  try {
    return await run(directory);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

async function readNativePages(directory, prefix) {
  const names = (await readdir(directory))
    .filter((name) => name.startsWith(prefix) && name.endsWith(".png"))
    .sort(
      (left, right) =>
        Number(left.match(/(\d+)\.png$/)[1]) - Number(right.match(/(\d+)\.png$/)[1]),
    );
  return Promise.all(names.map((name) => readFile(join(directory, name))));
}

async function auditBrowserPdf(pdfPath, fixture) {
  try {
    const report = await auditWorkbookPdf(pdfPath, {
      scope: fixture.scope,
      edition: fixture.edition,
      lessons: fixture.bundle.lessons,
    });
    return { passed: true, pageCount: report.pageCount };
  } catch (error) {
    if (error instanceof WorkbookPdfAuditError) {
      return { passed: false, error: error.message };
    }
    throw error;
  }
}

/**
 * Compile one fixture with both renderers and compare what they produced.
 *
 * The browser compilation refuses any Typst diagnostic, so a returned result is
 * already a clean build; what remains to be judged is the audit and the two
 * comparisons.
 */
export async function verifyWorkbookFixture(
  compiler,
  fixture,
  { directory, ppi = DEFAULT_COMPARISON_PPI, comparePixels = true },
) {
  const bundlePath = join(directory, `${fixture.id}.json`);
  const browserPdfPath = join(directory, `${fixture.id}-browser.pdf`);
  const nativePdfPath = join(directory, `${fixture.id}-native.pdf`);
  await writeFile(bundlePath, `${JSON.stringify(fixture.bundle, null, 2)}\n`);

  const browserStartedAt = Date.now();
  const browserPdf = await compileWorkbookPdf(compiler, fixture.bundle);
  const browserMilliseconds = Date.now() - browserStartedAt;
  await writeFile(browserPdfPath, browserPdf);

  const nativeStartedAt = Date.now();
  await compileBundleWithNativeTypst(bundlePath, nativePdfPath);
  const nativeMilliseconds = Date.now() - nativeStartedAt;

  const audit = await auditBrowserPdf(browserPdfPath, fixture);
  const text = await comparePdfDocuments(nativePdfPath, browserPdfPath);

  let pixels = null;
  if (comparePixels) {
    const browserPages = await compileWorkbookPages(compiler, fixture.bundle, { ppi });
    await compileBundleWithNativeTypst(
      bundlePath,
      join(directory, `${fixture.id}-native-{p}.png`),
      { ppi },
    );
    pixels = comparePagePixels(
      await readNativePages(directory, `${fixture.id}-native-`),
      browserPages.map(({ png }) => png),
    );
    pixels.ppi = ppi;
  }

  return {
    fixture,
    pageCount: text.pageCount,
    browserMilliseconds,
    nativeMilliseconds,
    browserBytes: browserPdf.byteLength,
    engines: {
      browser: readPdfCreator(browserPdf),
      native: readPdfCreator(await readFile(nativePdfPath)),
    },
    audit,
    text,
    pixels,
    passed: audit.passed && text.identical && (pixels === null || pixels.identical),
  };
}
