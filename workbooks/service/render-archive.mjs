import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, join } from "node:path";

import JSZip from "jszip";

import { buildWorkbookPdfs } from "../lib/build.mjs";
import {
  readWorkbookSheet,
  writeWorkbookPackage,
} from "../lib/sheet-import.mjs";

/**
 * Convert an exported Google Sheets workbook into the complete set of audited
 * student and teacher PDFs, returned as one ZIP archive.
 */
export async function renderWorkbookArchive(
  spreadsheetBytes,
  { workbookId } = {},
) {
  const input = Buffer.from(spreadsheetBytes);
  if (input.length === 0) {
    throw new TypeError("The workbook spreadsheet is empty.");
  }

  const temporaryRoot = await mkdtemp(join(tmpdir(), "4steps-render-service-"));
  const spreadsheetPath = join(temporaryRoot, "workbook.xlsx");
  const packageDirectory = join(temporaryRoot, "content-package");
  const pdfDirectory = join(temporaryRoot, "pdfs");

  try {
    await writeFile(spreadsheetPath, input);
    const sheetPackage = await readWorkbookSheet(spreadsheetPath, {
      workbookId,
    });
    const imported = await writeWorkbookPackage(
      sheetPackage,
      packageDirectory,
    );
    const targets = await buildWorkbookPdfs(imported.manifestPath, {
      outputDirectory: pdfDirectory,
    });

    const archive = new JSZip();
    const pdfNames = [];
    for (const target of targets) {
      const fileName = basename(target.outputPath);
      pdfNames.push(fileName);
      archive.file(fileName, await readFile(target.outputPath));
    }
    archive.file(
      "build.json",
      `${JSON.stringify(
        {
          schemaVersion: 1,
          workbookId: sheetPackage.manifest.id,
          bookTitle: sheetPackage.manifest.bookTitle,
          lessonCount: sheetPackage.lessons.length,
          pdfFiles: pdfNames,
        },
        null,
        2,
      )}\n`,
    );

    return {
      archive: await archive.generateAsync({
        type: "nodebuffer",
        compression: "DEFLATE",
        compressionOptions: { level: 6 },
      }),
      bookTitle: sheetPackage.manifest.bookTitle,
      lessonCount: sheetPackage.lessons.length,
      pdfNames,
      workbookId: sheetPackage.manifest.id,
    };
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
}
