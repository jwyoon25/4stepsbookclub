import { createHash } from "node:crypto";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import ExcelJS from "exceljs";

import { loadWorkbookPackage } from "./content.mjs";

const HEADER_ROW = 4;
const FIRST_DATA_ROW = 5;

const SHEET_HEADERS = Object.freeze({
  Workbook: [
    "Status",
    "Book title",
    "Author",
    "Series title",
    "Lesson range",
    "Cover subtitle / description",
  ],
  Lessons: [
    "Status",
    "Lesson number",
    "Lesson title",
    "Chapter or page range",
    "Framing note / introduction",
    "General student instructions",
  ],
  Comprehension: [
    "Status",
    "Lesson number",
    "Order",
    "Question",
    "Quotation (optional)",
    "Guidance & requirements (one item per line)",
    "Teacher guidance",
    "Response space",
    "Custom lines",
    "Total response pages",
  ],
  Analysis: [
    "Status",
    "Lesson number",
    "Order",
    "Question",
    "Quotation (optional)",
    "Guidance & requirements (one item per line)",
    "Teacher guidance",
    "Response space",
    "Custom lines",
    "Total response pages",
  ],
  Writing: [
    "Status",
    "Lesson number",
    "Order",
    "Writing prompt",
    "Guidance & requirements (one item per line)",
    "Teacher guidance (optional)",
    "Example structure or rubric (optional)",
    "Response space",
    "Custom lines",
    "Total response pages",
  ],
  Vocabulary: [
    "Status",
    "Lesson number",
    "Order",
    "Vocabulary word",
    "Korean meaning",
    "English definition",
    "Excerpt from the book",
    "Excerpt context",
    "Chapter reference (optional)",
  ],
});

const RESPONSE_MODES = Object.freeze({
  "Short answer": "short-answer",
  "Short paragraph": "short-paragraph",
  "Extended answer": "extended-answer",
  "Full page": "full-page",
  "Multiple pages": "multiple-pages",
  "Custom lines": "custom-lines",
});

export class WorkbookSheetError extends Error {
  constructor(message, options) {
    super(message, options);
    this.name = "WorkbookSheetError";
  }
}

function location(sheetName, rowNumber, columnName) {
  return `"${sheetName}" row ${rowNumber}, ${columnName}`;
}

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

function cellValue(sheet, rowNumber, columnNumber) {
  return unwrapCellValue(sheet.getCell(rowNumber, columnNumber).value);
}

function isBlank(value) {
  return value === null || value === undefined || String(value).trim() === "";
}

function textValue(
  sheet,
  rowNumber,
  columnNumber,
  columnName,
  { required = false } = {},
) {
  const value = cellValue(sheet, rowNumber, columnNumber);
  const cellLocation = location(sheet.name, rowNumber, columnName);

  if (isBlank(value)) {
    if (required) {
      throw new WorkbookSheetError(`${cellLocation} is required.`);
    }
    return undefined;
  }

  if (value instanceof Date || typeof value === "object") {
    throw new WorkbookSheetError(`${cellLocation} must contain text.`);
  }

  return String(value);
}

function integerValue(
  sheet,
  rowNumber,
  columnNumber,
  columnName,
  { required = false, minimum = 1 } = {},
) {
  const value = cellValue(sheet, rowNumber, columnNumber);
  const cellLocation = location(sheet.name, rowNumber, columnName);

  if (isBlank(value)) {
    if (required) {
      throw new WorkbookSheetError(`${cellLocation} is required.`);
    }
    return undefined;
  }

  const normalizedValue = String(value).trim();
  const number = typeof value === "number" ? value : Number(normalizedValue);
  if (typeof value !== "number" && !/^\d+$/u.test(normalizedValue)) {
    throw new WorkbookSheetError(
      `${cellLocation} must be a whole number of at least ${minimum}.`,
    );
  }
  if (!Number.isInteger(number) || number < minimum) {
    throw new WorkbookSheetError(
      `${cellLocation} must be a whole number of at least ${minimum}.`,
    );
  }

  return number;
}

function optionalProperty(target, key, value) {
  if (value !== undefined) {
    target[key] = value;
  }
}

function guidanceValue(sheet, rowNumber, columnNumber, columnName) {
  const value = textValue(sheet, rowNumber, columnNumber, columnName);
  if (value === undefined) {
    return undefined;
  }

  const items = value.split(/\r?\n/u).filter((item) => item.trim() !== "");
  return items.length > 0 ? items : undefined;
}

function responseSpaceValue(sheet, rowNumber) {
  const modeLabel = textValue(sheet, rowNumber, 8, "Response space");
  const lines = integerValue(sheet, rowNumber, 9, "Custom lines");
  const pages = integerValue(sheet, rowNumber, 10, "Total response pages");

  if (modeLabel === undefined) {
    if (lines !== undefined || pages !== undefined) {
      throw new WorkbookSheetError(
        `${location(sheet.name, rowNumber, "Response space")} must be set before entering Custom lines or Total response pages.`,
      );
    }
    return undefined;
  }

  const normalizedLabel = modeLabel.trim();
  const mode = RESPONSE_MODES[normalizedLabel];
  if (!mode) {
    throw new WorkbookSheetError(
      `${location(sheet.name, rowNumber, "Response space")} must use one of the template dropdown choices.`,
    );
  }

  if (mode === "custom-lines") {
    if (lines === undefined) {
      throw new WorkbookSheetError(
        `${location(sheet.name, rowNumber, "Custom lines")} is required for Custom lines.`,
      );
    }
    if (pages !== undefined) {
      throw new WorkbookSheetError(
        `${location(sheet.name, rowNumber, "Total response pages")} must be blank for Custom lines.`,
      );
    }
    return { mode, lines };
  }

  if (mode === "multiple-pages") {
    if (pages === undefined || pages < 2) {
      throw new WorkbookSheetError(
        `${location(sheet.name, rowNumber, "Total response pages")} must be a whole number of at least 2 for Multiple pages.`,
      );
    }
    if (lines !== undefined) {
      throw new WorkbookSheetError(
        `${location(sheet.name, rowNumber, "Custom lines")} must be blank for Multiple pages.`,
      );
    }
    return { mode, pages };
  }

  if (lines !== undefined || pages !== undefined) {
    throw new WorkbookSheetError(
      `${location(sheet.name, rowNumber, "Custom lines / Total response pages")} must be blank for ${normalizedLabel}.`,
    );
  }

  return { mode };
}

function requireSheet(workbook, sheetName) {
  const sheet = workbook.getWorksheet(sheetName);
  if (!sheet) {
    throw new WorkbookSheetError(
      `Required tab "${sheetName}" is missing. Start from the official template and do not rename tabs.`,
    );
  }

  const expectedHeaders = SHEET_HEADERS[sheetName];
  expectedHeaders.forEach((expected, index) => {
    const actual = cellValue(sheet, HEADER_ROW, index + 1);
    if (actual !== expected) {
      throw new WorkbookSheetError(
        `"${sheetName}" column ${index + 1} must be named "${expected}"; found ${JSON.stringify(actual)}.`,
      );
    }
  });

  return sheet;
}

function dataRows(sheet, columnCount) {
  const rows = [];
  for (
    let rowNumber = FIRST_DATA_ROW;
    rowNumber <= sheet.rowCount;
    rowNumber += 1
  ) {
    const hasContent = Array.from(
      { length: columnCount - 1 },
      (_, index) => cellValue(sheet, rowNumber, index + 2),
    ).some((value) => !isBlank(value));

    if (hasContent) {
      rows.push(rowNumber);
    }
  }
  return rows;
}

function slugify(value) {
  const slug = value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/gu, "-")
    .replace(/^-+|-+$/gu, "");

  if (slug) {
    return slug;
  }

  const suffix = createHash("sha256").update(value).digest("hex").slice(0, 8);
  return `workbook-${suffix}`;
}

function validateWorkbookId(workbookId) {
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/u.test(workbookId)) {
    throw new WorkbookSheetError(
      `Workbook ID "${workbookId}" is invalid. Use lowercase letters, numbers, and single hyphens only.`,
    );
  }
  return workbookId;
}

function parseWorkbookMetadata(sheet) {
  const rows = dataRows(sheet, SHEET_HEADERS.Workbook.length);
  if (rows.length !== 1) {
    throw new WorkbookSheetError(
      `"Workbook" must contain exactly one information row; found ${rows.length}.`,
    );
  }

  const rowNumber = rows[0];
  const metadata = {
    bookTitle: textValue(sheet, rowNumber, 2, "Book title", { required: true }),
    author: textValue(sheet, rowNumber, 3, "Author", { required: true }),
    seriesTitle: textValue(sheet, rowNumber, 4, "Series title", {
      required: true,
    }),
    lessonRange: textValue(sheet, rowNumber, 5, "Lesson range", {
      required: true,
    }),
  };
  optionalProperty(
    metadata,
    "coverSubtitle",
    textValue(sheet, rowNumber, 6, "Cover subtitle / description"),
  );
  return metadata;
}

function parseLessons(sheet) {
  const rows = dataRows(sheet, SHEET_HEADERS.Lessons.length);
  if (rows.length === 0) {
    throw new WorkbookSheetError('"Lessons" must contain at least one lesson row.');
  }

  const lessons = [];
  const lessonNumbers = new Map();
  for (const rowNumber of rows) {
    const lessonNumber = integerValue(
      sheet,
      rowNumber,
      2,
      "Lesson number",
      { required: true },
    );
    if (lessonNumbers.has(lessonNumber)) {
      throw new WorkbookSheetError(
        `"Lessons" row ${rowNumber} duplicates lesson number ${lessonNumber} from row ${lessonNumbers.get(lessonNumber)}.`,
      );
    }
    lessonNumbers.set(lessonNumber, rowNumber);

    const lesson = {
      $schema: "../../../schema/lesson.schema.json",
      schemaVersion: 1,
      lessonNumber,
      title: textValue(sheet, rowNumber, 3, "Lesson title", { required: true }),
      readingRange: textValue(sheet, rowNumber, 4, "Chapter or page range", {
        required: true,
      }),
      sections: {
        readingComprehension: [],
        criticalThinkingAndAnalysis: [],
        paragraphWriting: [],
        vocabulary: [],
      },
    };
    optionalProperty(
      lesson,
      "framingNote",
      textValue(sheet, rowNumber, 5, "Framing note / introduction"),
    );
    optionalProperty(
      lesson,
      "studentInstructions",
      textValue(sheet, rowNumber, 6, "General student instructions"),
    );
    lessons.push(lesson);
  }

  return { lessons, lessonNumbers };
}

function addOrderedItem(sectionRows, lessonNumber, order, rowNumber, item, sheet) {
  const rowsForLesson = sectionRows.get(lessonNumber) ?? [];
  const duplicate = rowsForLesson.find((row) => row.order === order);
  if (duplicate) {
    throw new WorkbookSheetError(
      `"${sheet.name}" row ${rowNumber} duplicates order ${order} for lesson ${lessonNumber} from row ${duplicate.rowNumber}.`,
    );
  }
  rowsForLesson.push({ item, order, rowNumber });
  sectionRows.set(lessonNumber, rowsForLesson);
}

function assertKnownLesson(sheet, rowNumber, lessonNumber, lessonNumbers) {
  if (!lessonNumbers.has(lessonNumber)) {
    throw new WorkbookSheetError(
      `"${sheet.name}" row ${rowNumber} refers to lesson ${lessonNumber}, which is not listed on the Lessons tab.`,
    );
  }
}

function parseQuestionSheet(sheet, lessonNumbers) {
  const sectionRows = new Map();
  for (const rowNumber of dataRows(sheet, SHEET_HEADERS[sheet.name].length)) {
    const lessonNumber = integerValue(sheet, rowNumber, 2, "Lesson number", {
      required: true,
    });
    const order = integerValue(sheet, rowNumber, 3, "Order", { required: true });
    assertKnownLesson(sheet, rowNumber, lessonNumber, lessonNumbers);

    const item = {
      prompt: textValue(sheet, rowNumber, 4, "Question", { required: true }),
      teacherGuidance: textValue(sheet, rowNumber, 7, "Teacher guidance", {
        required: true,
      }),
    };
    optionalProperty(
      item,
      "quotation",
      textValue(sheet, rowNumber, 5, "Quotation (optional)"),
    );
    optionalProperty(
      item,
      "responseGuidance",
      guidanceValue(
        sheet,
        rowNumber,
        6,
        "Guidance & requirements (one item per line)",
      ),
    );
    optionalProperty(item, "responseSpace", responseSpaceValue(sheet, rowNumber));
    addOrderedItem(sectionRows, lessonNumber, order, rowNumber, item, sheet);
  }
  return sectionRows;
}

function parseWritingSheet(sheet, lessonNumbers) {
  const sectionRows = new Map();
  for (const rowNumber of dataRows(sheet, SHEET_HEADERS.Writing.length)) {
    const lessonNumber = integerValue(sheet, rowNumber, 2, "Lesson number", {
      required: true,
    });
    const order = integerValue(sheet, rowNumber, 3, "Order", { required: true });
    assertKnownLesson(sheet, rowNumber, lessonNumber, lessonNumbers);

    const item = {
      prompt: textValue(sheet, rowNumber, 4, "Writing prompt", {
        required: true,
      }),
    };
    optionalProperty(
      item,
      "responseGuidance",
      guidanceValue(
        sheet,
        rowNumber,
        5,
        "Guidance & requirements (one item per line)",
      ),
    );
    optionalProperty(
      item,
      "teacherGuidance",
      textValue(sheet, rowNumber, 6, "Teacher guidance (optional)"),
    );
    optionalProperty(
      item,
      "exampleStructureOrRubric",
      textValue(sheet, rowNumber, 7, "Example structure or rubric (optional)"),
    );
    optionalProperty(item, "responseSpace", responseSpaceValue(sheet, rowNumber));
    addOrderedItem(sectionRows, lessonNumber, order, rowNumber, item, sheet);
  }
  return sectionRows;
}

function parseVocabularySheet(sheet, lessonNumbers) {
  const sectionRows = new Map();
  for (const rowNumber of dataRows(sheet, SHEET_HEADERS.Vocabulary.length)) {
    const lessonNumber = integerValue(sheet, rowNumber, 2, "Lesson number", {
      required: true,
    });
    const order = integerValue(sheet, rowNumber, 3, "Order", { required: true });
    assertKnownLesson(sheet, rowNumber, lessonNumber, lessonNumbers);

    const item = {
      term: textValue(sheet, rowNumber, 4, "Vocabulary word", { required: true }),
      koreanMeaning: textValue(sheet, rowNumber, 5, "Korean meaning", {
        required: true,
      }),
      definition: textValue(sheet, rowNumber, 6, "English definition", {
        required: true,
      }),
      bookExcerpt: textValue(sheet, rowNumber, 7, "Excerpt from the book", {
        required: true,
      }),
      excerptContext: textValue(sheet, rowNumber, 8, "Excerpt context", {
        required: true,
      }),
    };
    optionalProperty(
      item,
      "chapterReference",
      textValue(sheet, rowNumber, 9, "Chapter reference (optional)"),
    );
    addOrderedItem(sectionRows, lessonNumber, order, rowNumber, item, sheet);
  }
  return sectionRows;
}

function assignSection(lessons, sectionRows, sectionKey, sheetName) {
  for (const lesson of lessons) {
    const rows = sectionRows.get(lesson.lessonNumber) ?? [];
    if (rows.length === 0) {
      throw new WorkbookSheetError(
        `Lesson ${lesson.lessonNumber} needs at least one row on the "${sheetName}" tab.`,
      );
    }
    lesson.sections[sectionKey] = rows
      .sort((left, right) => left.order - right.order)
      .map(({ item }) => item);
  }
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

  const sheets = Object.fromEntries(
    Object.keys(SHEET_HEADERS).map((sheetName) => [
      sheetName,
      requireSheet(spreadsheet, sheetName),
    ]),
  );
  const metadata = parseWorkbookMetadata(sheets.Workbook);
  const { lessons, lessonNumbers } = parseLessons(sheets.Lessons);

  assignSection(
    lessons,
    parseQuestionSheet(sheets.Comprehension, lessonNumbers),
    "readingComprehension",
    "Comprehension",
  );
  assignSection(
    lessons,
    parseQuestionSheet(sheets.Analysis, lessonNumbers),
    "criticalThinkingAndAnalysis",
    "Analysis",
  );
  assignSection(
    lessons,
    parseWritingSheet(sheets.Writing, lessonNumbers),
    "paragraphWriting",
    "Writing",
  );
  assignSection(
    lessons,
    parseVocabularySheet(sheets.Vocabulary, lessonNumbers),
    "vocabulary",
    "Vocabulary",
  );

  const id = validateWorkbookId(workbookId ?? slugify(metadata.bookTitle));
  const lessonFiles = lessons.map(
    ({ lessonNumber }) =>
      `lessons/lesson-${String(lessonNumber).padStart(2, "0")}.json`,
  );

  return {
    manifest: {
      $schema: "../../schema/workbook.schema.json",
      schemaVersion: 1,
      id,
      ...metadata,
      lessonFiles,
    },
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
