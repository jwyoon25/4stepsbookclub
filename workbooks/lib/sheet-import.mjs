// ---------------------------------------------------------------------------
// The `.xlsx` adapter for the Google Sheets authoring contract.
//
// Everything about which tabs exist, what their columns mean, and how a row
// becomes schema-v1 content lives in `builder/browser/sheet-contract.mjs`, so
// that the command line, the render service, and the browser preview all read
// the same workbook the same way. What is left here is the part that is
// genuinely about Excel files: turning a downloaded spreadsheet into plain cell
// matrices, choosing an identifier for the package, and writing it to disk only
// after it validates.
// ---------------------------------------------------------------------------

import { createHash } from "node:crypto";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import ExcelJS from "exceljs";

import {
  createWorkbookManifest,
  parseWorkbookGrids,
  SHEET_HEADERS,
  SHEET_NAMES,
  slugifyBookTitle,
  validateWorkbookId,
  WorkbookSheetError,
} from "../builder/browser/sheet-contract.mjs";
import { loadWorkbookPackage } from "./content.mjs";

export { WorkbookSheetError };

/**
 * Reduce one ExcelJS cell to the primitive a Google Sheet would have returned.
 *
 * Apps Script hands over plain values; ExcelJS hands over formula results, rich
 * text runs, and hyperlink objects. Flattening them here is what lets the
 * contract itself stay free of any spreadsheet library.
 */
function unwrapCellValue(value) {
  if (value === null || value === undefined) {
    return "";
  }

  if (typeof value !== "object" || value instanceof Date) {
    return value;
  }

  if (Object.hasOwn(value, "result")) {
    return unwrapCellValue(value.result);
  }

  if (Array.isArray(value.richText)) {
    return value.richText.map((part) => part.text ?? "").join("");
  }

  if (typeof value.text === "string") {
    return value.text;
  }

  return value;
}

/**
 * Read every tab the contract expects into a cell matrix.
 *
 * A tab that is missing is simply absent from the result; the contract reports
 * it, so the message an author sees does not depend on which adapter read the
 * file.
 */
function readWorkbookGrids(spreadsheet) {
  const grids = {};

  for (const sheetName of SHEET_NAMES) {
    const sheet = spreadsheet.getWorksheet(sheetName);
    if (!sheet) {
      continue;
    }

    const columnCount = SHEET_HEADERS[sheetName].length;
    grids[sheetName] = Array.from({ length: sheet.rowCount }, (_, rowIndex) =>
      Array.from({ length: columnCount }, (_, columnIndex) =>
        unwrapCellValue(sheet.getCell(rowIndex + 1, columnIndex + 1).value),
      ),
    );
  }

  return grids;
}

/**
 * Choose the package identifier for a parsed workbook.
 *
 * A title with no sluggable characters — one written entirely in Hangul, for
 * instance — still needs a stable identifier, so it falls back to a digest of
 * the title rather than to a name that changes between imports.
 */
function resolveWorkbookId(bookTitle, workbookId) {
  if (workbookId) {
    return validateWorkbookId(workbookId);
  }

  const slug = slugifyBookTitle(bookTitle);
  if (slug) {
    return validateWorkbookId(slug);
  }

  const suffix = createHash("sha256").update(bookTitle).digest("hex").slice(0, 8);
  return validateWorkbookId(`workbook-${suffix}`);
}

/**
 * Read the fixed Google Sheets MVP contract and convert it to schema-v1 data.
 */
export async function readWorkbookSheet(inputPath, { workbookId } = {}) {
  const absoluteInputPath = resolve(inputPath);
  const spreadsheet = new ExcelJS.Workbook();
  try {
    await spreadsheet.xlsx.readFile(absoluteInputPath);
  } catch (cause) {
    throw new WorkbookSheetError(
      `Could not read workbook spreadsheet: ${absoluteInputPath}`,
      { cause },
    );
  }

  const { metadata, lessons } = parseWorkbookGrids(readWorkbookGrids(spreadsheet));

  return {
    manifest: createWorkbookManifest(metadata, lessons, {
      workbookId: resolveWorkbookId(metadata.bookTitle, workbookId),
    }),
    lessons,
    sourcePath: absoluteInputPath,
  };
}

async function writeJson(filePath, value) {
  await writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`);
}

/**
 * Validate in a temporary package before writing any production content files.
 */
export async function writeWorkbookPackage(sheetPackage, outputDirectory) {
  const absoluteOutputDirectory = resolve(outputDirectory);
  const temporaryRoot = await mkdtemp(join(tmpdir(), "4steps-sheet-import-"));
  const stagedDirectory = join(temporaryRoot, sheetPackage.manifest.id);
  const stagedManifestPath = join(stagedDirectory, "workbook.json");

  try {
    await mkdir(join(stagedDirectory, "lessons"), { recursive: true });
    await writeJson(stagedManifestPath, sheetPackage.manifest);
    await Promise.all(
      sheetPackage.lessons.map((lesson, index) =>
        writeJson(
          join(stagedDirectory, sheetPackage.manifest.lessonFiles[index]),
          lesson,
        ),
      ),
    );
    await loadWorkbookPackage(stagedManifestPath);

    await mkdir(join(absoluteOutputDirectory, "lessons"), { recursive: true });
    const manifestPath = join(absoluteOutputDirectory, "workbook.json");
    await writeJson(manifestPath, sheetPackage.manifest);
    await Promise.all(
      sheetPackage.lessons.map((lesson, index) =>
        writeJson(
          join(absoluteOutputDirectory, sheetPackage.manifest.lessonFiles[index]),
          lesson,
        ),
      ),
    );
    await loadWorkbookPackage(manifestPath);

    return {
      manifestPath,
      lessonCount: sheetPackage.lessons.length,
      outputDirectory: absoluteOutputDirectory,
    };
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
}

export async function importWorkbookSheet(
  inputPath,
  { workbookId, outputDirectory } = {},
) {
  const sheetPackage = await readWorkbookSheet(inputPath, { workbookId });
  const destination =
    outputDirectory ??
    resolve(
      dirname(dirname(fileURLToPath(import.meta.url))),
      "content",
      sheetPackage.manifest.id,
    );
  return writeWorkbookPackage(sheetPackage, destination);
}
