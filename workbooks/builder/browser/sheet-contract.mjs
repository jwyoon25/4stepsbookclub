// ---------------------------------------------------------------------------
// The Google Sheets authoring contract, as pure data conversion.
//
// This is the one definition of which tabs a workbook has, what their columns
// mean, and how a row becomes schema-v1 content. It reads cell matrices and
// nothing else: no spreadsheet library, no filesystem, no Node. That is what
// lets the same contract run in three places without a second content model —
// the `.xlsx` importer behind the command line, the Apps Script adapter that
// reads the live Sheet, and the preview window that compiles what it sees.
//
// Every message names the tab, the row, and the column, because a tutor fixing
// a workbook needs to be told which cell to open.
//
// A grid is `{ name, rows }`, where `rows` is a zero-indexed array of row
// arrays. Row and column numbers in this file stay one-based throughout, the
// way a spreadsheet numbers them and the way the messages report them.
// ---------------------------------------------------------------------------

export const HEADER_ROW = 4;
export const FIRST_DATA_ROW = 5;

export const SHEET_HEADERS = Object.freeze({
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

export const SHEET_NAMES = Object.freeze(Object.keys(SHEET_HEADERS));

export const RESPONSE_MODES = Object.freeze({
  "Short answer": "short-answer",
  "Short paragraph": "short-paragraph",
  "Extended answer": "extended-answer",
  "Full page": "full-page",
  "Multiple pages": "multiple-pages",
  "Custom lines": "custom-lines",
});

/**
 * A workbook the Sheet cannot describe.
 *
 * The message names the cell so an author reading it knows where to look, and
 * `cell` says the same thing in numbers so the Sheet itself can be made to
 * point at it. Some problems are a whole tab's — a missing one, or a lesson
 * with no questions anywhere — and carry no row.
 */
export class WorkbookSheetError extends Error {
  constructor(message, { cell, ...options } = {}) {
    super(message, options);
    this.name = "WorkbookSheetError";
    this.cell = cell;
  }
}

function location(sheetName, rowNumber, columnName) {
  return `"${sheetName}" row ${rowNumber}, ${columnName}`;
}

/** A problem with one cell, named in prose and in coordinates. */
function cellError(grid, rowNumber, columnNumber, columnName, problem) {
  return new WorkbookSheetError(
    `${location(grid.name, rowNumber, columnName)} ${problem}`,
    { cell: { sheet: grid.name, row: rowNumber, column: columnNumber } },
  );
}

/** A problem with one row that no single column is responsible for. */
function rowError(grid, rowNumber, columnNumber, message) {
  return new WorkbookSheetError(message, {
    cell: { sheet: grid.name, row: rowNumber, column: columnNumber },
  });
}

function cellValue(grid, rowNumber, columnNumber) {
  const value = grid.rows[rowNumber - 1]?.[columnNumber - 1];
  return value === null || value === undefined ? "" : value;
}

function isBlank(value) {
  return value === null || value === undefined || String(value).trim() === "";
}

function textValue(grid, rowNumber, columnNumber, columnName, { required = false } = {}) {
  const value = cellValue(grid, rowNumber, columnNumber);

  if (isBlank(value)) {
    if (required) {
      throw cellError(grid, rowNumber, columnNumber, columnName, "is required.");
    }
    return undefined;
  }

  if (value instanceof Date || typeof value === "object") {
    throw cellError(grid, rowNumber, columnNumber, columnName, "must contain text.");
  }

  return String(value);
}

function integerValue(
  grid,
  rowNumber,
  columnNumber,
  columnName,
  { required = false, minimum = 1 } = {},
) {
  const value = cellValue(grid, rowNumber, columnNumber);

  if (isBlank(value)) {
    if (required) {
      throw cellError(grid, rowNumber, columnNumber, columnName, "is required.");
    }
    return undefined;
  }

  const normalizedValue = String(value).trim();
  const number = typeof value === "number" ? value : Number(normalizedValue);
  const wholeNumber =
    (typeof value === "number" || /^\d+$/u.test(normalizedValue)) &&
    Number.isInteger(number) &&
    number >= minimum;
  if (!wholeNumber) {
    throw cellError(
      grid,
      rowNumber,
      columnNumber,
      columnName,
      `must be a whole number of at least ${minimum}.`,
    );
  }

  return number;
}

function optionalProperty(target, key, value) {
  if (value !== undefined) {
    target[key] = value;
  }
}

function guidanceValue(grid, rowNumber, columnNumber, columnName) {
  const value = textValue(grid, rowNumber, columnNumber, columnName);
  if (value === undefined) {
    return undefined;
  }

  const items = value.split(/\r?\n/u).filter((item) => item.trim() !== "");
  return items.length > 0 ? items : undefined;
}

function responseSpaceValue(grid, rowNumber) {
  const modeLabel = textValue(grid, rowNumber, 8, "Response space");
  const lines = integerValue(grid, rowNumber, 9, "Custom lines", { minimum: 0 });
  const pages = integerValue(grid, rowNumber, 10, "Total response pages");

  if (modeLabel === undefined) {
    if (lines !== undefined || pages !== undefined) {
      throw cellError(
        grid,
        rowNumber,
        8,
        "Response space",
        "must be set before entering Custom lines or Total response pages.",
      );
    }
    return undefined;
  }

  const normalizedLabel = modeLabel.trim();
  const mode = RESPONSE_MODES[normalizedLabel];
  if (!mode) {
    throw cellError(
      grid,
      rowNumber,
      8,
      "Response space",
      "must use one of the template dropdown choices.",
    );
  }

  if (mode === "custom-lines") {
    if (lines === undefined) {
      throw cellError(
        grid,
        rowNumber,
        9,
        "Custom lines",
        "is required for Custom lines.",
      );
    }
    if (pages !== undefined) {
      throw cellError(
        grid,
        rowNumber,
        10,
        "Total response pages",
        "must be blank for Custom lines.",
      );
    }
    return { mode, lines };
  }

  if (mode === "multiple-pages") {
    if (pages === undefined || pages < 2) {
      throw cellError(
        grid,
        rowNumber,
        10,
        "Total response pages",
        "must be a whole number of at least 2 for Multiple pages.",
      );
    }
    if (lines !== undefined) {
      throw cellError(
        grid,
        rowNumber,
        9,
        "Custom lines",
        "must be blank for Multiple pages.",
      );
    }
    return { mode, pages };
  }

  if (lines !== undefined || pages !== undefined) {
    throw cellError(
      grid,
      rowNumber,
      lines === undefined ? 10 : 9,
      "Custom lines / Total response pages",
      `must be blank for ${normalizedLabel}.`,
    );
  }

  return { mode };
}

function requireGrid(grids, sheetName) {
  const rows = grids[sheetName];
  if (!rows) {
    throw new WorkbookSheetError(
      `Required tab "${sheetName}" is missing. Start from the official template and do not rename tabs.`,
      { cell: { sheet: sheetName } },
    );
  }

  const grid = { name: sheetName, rows };
  SHEET_HEADERS[sheetName].forEach((expected, index) => {
    const actual = cellValue(grid, HEADER_ROW, index + 1);
    if (actual !== expected) {
      throw new WorkbookSheetError(
        `"${sheetName}" column ${index + 1} must be named "${expected}"; found ${JSON.stringify(actual)}.`,
        { cell: { sheet: sheetName, row: HEADER_ROW, column: index + 1 } },
      );
    }
  });

  return grid;
}

function dataRows(grid, columnCount) {
  const rows = [];
  for (let rowNumber = FIRST_DATA_ROW; rowNumber <= grid.rows.length; rowNumber += 1) {
    const hasContent = Array.from({ length: columnCount - 1 }, (_, index) =>
      cellValue(grid, rowNumber, index + 2),
    ).some((value) => !isBlank(value));

    if (hasContent) {
      rows.push(rowNumber);
    }
  }
  return rows;
}

/**
 * Turn a book title into a workbook ID.
 *
 * Returns an empty string when the title has nothing sluggable in it, such as a
 * title written entirely in Hangul. The caller decides what to do about that,
 * because an identifier is a packaging concern rather than part of the content
 * contract.
 */
export function slugifyBookTitle(value) {
  return String(value)
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/gu, "-")
    .replace(/^-+|-+$/gu, "");
}

export function validateWorkbookId(workbookId) {
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/u.test(workbookId)) {
    throw new WorkbookSheetError(
      `Workbook ID "${workbookId}" is invalid. Use lowercase letters, numbers, and single hyphens only.`,
    );
  }
  return workbookId;
}

function parseWorkbookMetadata(grid) {
  const rows = dataRows(grid, SHEET_HEADERS.Workbook.length);
  if (rows.length !== 1) {
    throw new WorkbookSheetError(
      `"Workbook" must contain exactly one information row; found ${rows.length}.`,
      { cell: { sheet: grid.name, row: FIRST_DATA_ROW } },
    );
  }

  const rowNumber = rows[0];
  const metadata = {
    bookTitle: textValue(grid, rowNumber, 2, "Book title", { required: true }),
    author: textValue(grid, rowNumber, 3, "Author", { required: true }),
    seriesTitle: textValue(grid, rowNumber, 4, "Series title", { required: true }),
    lessonRange: textValue(grid, rowNumber, 5, "Lesson range", { required: true }),
  };
  optionalProperty(
    metadata,
    "coverSubtitle",
    textValue(grid, rowNumber, 6, "Cover subtitle / description"),
  );
  return metadata;
}

function parseLessons(grid) {
  const rows = dataRows(grid, SHEET_HEADERS.Lessons.length);
  if (rows.length === 0) {
    throw new WorkbookSheetError('"Lessons" must contain at least one lesson row.', {
      cell: { sheet: grid.name, row: FIRST_DATA_ROW },
    });
  }

  const lessons = [];
  const lessonNumbers = new Map();
  for (const rowNumber of rows) {
    const lessonNumber = integerValue(grid, rowNumber, 2, "Lesson number", {
      required: true,
    });
    if (lessonNumbers.has(lessonNumber)) {
      throw rowError(
        grid,
        rowNumber,
        2,
        `"Lessons" row ${rowNumber} duplicates lesson number ${lessonNumber} from row ${lessonNumbers.get(lessonNumber)}.`,
      );
    }
    lessonNumbers.set(lessonNumber, rowNumber);

    const lesson = {
      $schema: "../../../schema/lesson.schema.json",
      schemaVersion: 1,
      lessonNumber,
      title: textValue(grid, rowNumber, 3, "Lesson title", { required: true }),
      readingRange: textValue(grid, rowNumber, 4, "Chapter or page range", {
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
      textValue(grid, rowNumber, 5, "Framing note / introduction"),
    );
    optionalProperty(
      lesson,
      "studentInstructions",
      textValue(grid, rowNumber, 6, "General student instructions"),
    );
    lessons.push(lesson);
  }

  return { lessons, lessonNumbers };
}

function addOrderedItem(sectionRows, lessonNumber, order, rowNumber, item, grid) {
  const rowsForLesson = sectionRows.get(lessonNumber) ?? [];
  const duplicate = rowsForLesson.find((row) => row.order === order);
  if (duplicate) {
    throw rowError(
      grid,
      rowNumber,
      3,
      `"${grid.name}" row ${rowNumber} duplicates order ${order} for lesson ${lessonNumber} from row ${duplicate.rowNumber}.`,
    );
  }
  rowsForLesson.push({ item, order, rowNumber });
  sectionRows.set(lessonNumber, rowsForLesson);
}

function assertKnownLesson(grid, rowNumber, lessonNumber, lessonNumbers) {
  if (!lessonNumbers.has(lessonNumber)) {
    throw rowError(
      grid,
      rowNumber,
      2,
      `"${grid.name}" row ${rowNumber} refers to lesson ${lessonNumber}, which is not listed on the Lessons tab.`,
    );
  }
}

function parseQuestionGrid(grid, lessonNumbers) {
  const sectionRows = new Map();
  for (const rowNumber of dataRows(grid, SHEET_HEADERS[grid.name].length)) {
    const lessonNumber = integerValue(grid, rowNumber, 2, "Lesson number", {
      required: true,
    });
    const order = integerValue(grid, rowNumber, 3, "Order", { required: true });
    assertKnownLesson(grid, rowNumber, lessonNumber, lessonNumbers);

    const item = {
      prompt: textValue(grid, rowNumber, 4, "Question", { required: true }),
      teacherGuidance: textValue(grid, rowNumber, 7, "Teacher guidance", {
        required: true,
      }),
    };
    optionalProperty(
      item,
      "quotation",
      textValue(grid, rowNumber, 5, "Quotation (optional)"),
    );
    optionalProperty(
      item,
      "responseGuidance",
      guidanceValue(grid, rowNumber, 6, "Guidance & requirements (one item per line)"),
    );
    optionalProperty(item, "responseSpace", responseSpaceValue(grid, rowNumber));
    addOrderedItem(sectionRows, lessonNumber, order, rowNumber, item, grid);
  }
  return sectionRows;
}

function parseWritingGrid(grid, lessonNumbers) {
  const sectionRows = new Map();
  for (const rowNumber of dataRows(grid, SHEET_HEADERS.Writing.length)) {
    const lessonNumber = integerValue(grid, rowNumber, 2, "Lesson number", {
      required: true,
    });
    const order = integerValue(grid, rowNumber, 3, "Order", { required: true });
    assertKnownLesson(grid, rowNumber, lessonNumber, lessonNumbers);

    const item = {
      prompt: textValue(grid, rowNumber, 4, "Writing prompt", { required: true }),
    };
    optionalProperty(
      item,
      "responseGuidance",
      guidanceValue(grid, rowNumber, 5, "Guidance & requirements (one item per line)"),
    );
    optionalProperty(
      item,
      "teacherGuidance",
      textValue(grid, rowNumber, 6, "Teacher guidance (optional)"),
    );
    optionalProperty(
      item,
      "exampleStructureOrRubric",
      textValue(grid, rowNumber, 7, "Example structure or rubric (optional)"),
    );
    optionalProperty(item, "responseSpace", responseSpaceValue(grid, rowNumber));
    addOrderedItem(sectionRows, lessonNumber, order, rowNumber, item, grid);
  }
  return sectionRows;
}

function parseVocabularyGrid(grid, lessonNumbers) {
  const sectionRows = new Map();
  for (const rowNumber of dataRows(grid, SHEET_HEADERS.Vocabulary.length)) {
    const lessonNumber = integerValue(grid, rowNumber, 2, "Lesson number", {
      required: true,
    });
    const order = integerValue(grid, rowNumber, 3, "Order", { required: true });
    assertKnownLesson(grid, rowNumber, lessonNumber, lessonNumbers);

    const item = {
      term: textValue(grid, rowNumber, 4, "Vocabulary word", { required: true }),
      koreanMeaning: textValue(grid, rowNumber, 5, "Korean meaning", {
        required: true,
      }),
      definition: textValue(grid, rowNumber, 6, "English definition", {
        required: true,
      }),
      bookExcerpt: textValue(grid, rowNumber, 7, "Excerpt from the book", {
        required: true,
      }),
      excerptContext: textValue(grid, rowNumber, 8, "Excerpt context", {
        required: true,
      }),
    };
    optionalProperty(
      item,
      "chapterReference",
      textValue(grid, rowNumber, 9, "Chapter reference (optional)"),
    );
    addOrderedItem(sectionRows, lessonNumber, order, rowNumber, item, grid);
  }
  return sectionRows;
}

function assignSection(lessons, sectionRows, sectionKey, sheetName, sources) {
  for (const lesson of lessons) {
    const rows = sectionRows.get(lesson.lessonNumber) ?? [];
    if (rows.length === 0) {
      throw new WorkbookSheetError(
        `Lesson ${lesson.lessonNumber} needs at least one row on the "${sheetName}" tab.`,
        { cell: { sheet: sheetName } },
      );
    }

    const ordered = rows.sort((left, right) => left.order - right.order);
    lesson.sections[sectionKey] = ordered.map(({ item }) => item);
    // The lesson holds items in this order from here on, so an index into a
    // section is the same index into these rows. That is the whole of what lets
    // a complaint about `/sections/vocabulary/2` be turned back into a cell.
    sources.get(lesson.lessonNumber).sections[sectionKey] = ordered.map(
      ({ rowNumber }) => ({ sheet: sheetName, row: rowNumber }),
    );
  }
}

/**
 * Convert the six tabs of the authoring template into schema-v1 content.
 *
 * `grids` maps each tab name to its cell matrix. The result carries the
 * workbook's metadata and its lessons in the order the Lessons tab lists them;
 * it has no identifier yet, because nothing in the Sheet decides that.
 *
 * `sources` says where each lesson and each of its items was typed. Nothing
 * about the content needs it — the renderer never sees it — but a rule that
 * fails later, when the content is no longer rows, can be pointed back at the
 * cell that broke it.
 */
export function parseWorkbookGrids(grids) {
  const sheets = Object.fromEntries(
    SHEET_NAMES.map((sheetName) => [sheetName, requireGrid(grids, sheetName)]),
  );
  const metadata = parseWorkbookMetadata(sheets.Workbook);
  const { lessons, lessonNumbers } = parseLessons(sheets.Lessons);

  const sources = new Map(
    [...lessonNumbers].map(([lessonNumber, rowNumber]) => [
      lessonNumber,
      { lesson: { sheet: "Lessons", row: rowNumber }, sections: {} },
    ]),
  );

  assignSection(
    lessons,
    parseQuestionGrid(sheets.Comprehension, lessonNumbers),
    "readingComprehension",
    "Comprehension",
    sources,
  );
  assignSection(
    lessons,
    parseQuestionGrid(sheets.Analysis, lessonNumbers),
    "criticalThinkingAndAnalysis",
    "Analysis",
    sources,
  );
  assignSection(
    lessons,
    parseWritingGrid(sheets.Writing, lessonNumbers),
    "paragraphWriting",
    "Writing",
    sources,
  );
  assignSection(
    lessons,
    parseVocabularyGrid(sheets.Vocabulary, lessonNumbers),
    "vocabulary",
    "Vocabulary",
    sources,
  );

  return { metadata, lessons, sources };
}

/**
 * Which cell a content rule was complaining about.
 *
 * `content-rules.mjs` reports the lesson and a path into it, because it never
 * saw a spreadsheet. This turns one of those paths back into a row: a section
 * item points at the row it was typed on, and anything else — the lesson cover,
 * the lesson as a whole — points at the lesson's own row.
 */
export function locateContentPath(sources, lessonNumber, path) {
  const lesson = sources?.get?.(lessonNumber);
  if (!lesson) {
    return undefined;
  }

  const [, sections, sectionKey, index] = String(path ?? "").split("/");
  if (sections !== "sections") {
    return lesson.lesson;
  }
  return lesson.sections[sectionKey]?.[Number(index)] ?? lesson.lesson;
}

/** Build the package manifest for parsed content under a chosen ID. */
export function createWorkbookManifest(metadata, lessons, { workbookId }) {
  return {
    $schema: "../../schema/workbook.schema.json",
    schemaVersion: 1,
    id: validateWorkbookId(workbookId),
    ...metadata,
    lessonFiles: lessons.map(
      ({ lessonNumber }) =>
        `lessons/lesson-${String(lessonNumber).padStart(2, "0")}.json`,
    ),
  };
}
