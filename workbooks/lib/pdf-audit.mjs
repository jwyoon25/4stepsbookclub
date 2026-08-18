import { readFile } from "node:fs/promises";

import { getDocument } from "pdfjs-dist/legacy/build/pdf.mjs";

const A4_WIDTH_POINTS = 595.276;
const A4_HEIGHT_POINTS = 841.89;
const PAGE_TOLERANCE_POINTS = 1;
const BOUNDS_TOLERANCE_POINTS = 1;

const SECTION_CHECKS = [
  {
    step: 1,
    band: "STEP1READ",
    name: "READINGCOMPREHENSION",
  },
  {
    step: 2,
    band: "STEP2THINK",
    name: "CRITICALTHINKINGANALYSIS",
  },
  {
    step: 3,
    band: "STEP3SPEAK",
    name: "PARAGRAPHWRITING",
  },
  {
    step: 4,
    band: "STEP4WRITE",
    name: "VOCABULARY",
  },
];

export class WorkbookPdfAuditError extends Error {
  constructor(message) {
    super(message);
    this.name = "WorkbookPdfAuditError";
  }
}

function canonicalText(value) {
  return value.toUpperCase().replace(/[^A-Z0-9]+/g, "");
}

function approximately(actual, expected, tolerance = PAGE_TOLERANCE_POINTS) {
  return Math.abs(actual - expected) <= tolerance;
}

function isUnrotatedText(item) {
  return (
    Math.abs(item.transform[1]) < 0.001 &&
    Math.abs(item.transform[2]) < 0.001
  );
}

function assertTextWithinPage(item, pageNumber, width, height, filePath) {
  if (!item.str || !isUnrotatedText(item)) {
    return;
  }

  const x = item.transform[4];
  const y = item.transform[5];
  const right = x + item.width;
  const top = y + item.height;
  if (
    x < -BOUNDS_TOLERANCE_POINTS ||
    right > width + BOUNDS_TOLERANCE_POINTS ||
    y < -BOUNDS_TOLERANCE_POINTS ||
    top > height + BOUNDS_TOLERANCE_POINTS
  ) {
    throw new WorkbookPdfAuditError(
      `PDF text leaves the page bounds in ${filePath} on page ${pageNumber}: ` +
        `${JSON.stringify(item.str.slice(0, 80))}.`,
    );
  }
}

export async function inspectWorkbookPdf(filePath) {
  const data = new Uint8Array(await readFile(filePath));
  const document = await getDocument({ data, disableWorker: true }).promise;

  try {
    const pages = [];
    for (let pageNumber = 1; pageNumber <= document.numPages; pageNumber += 1) {
      const page = await document.getPage(pageNumber);
      const viewport = page.getViewport({ scale: 1 });
      const textContent = await page.getTextContent();
      const items = textContent.items.filter((item) => "str" in item);
      const text = items.map(({ str }) => str).join(" ");
      const headerText = items
        .filter((item) => item.transform[5] >= viewport.height - 55)
        .map(({ str }) => str)
        .join(" ");

      pages.push({
        number: pageNumber,
        width: viewport.width,
        height: viewport.height,
        text,
        canonical: canonicalText(text),
        headerCanonical: canonicalText(headerText),
        items,
      });
    }

    return { pageCount: document.numPages, pages };
  } finally {
    await document.destroy();
  }
}

export async function auditWorkbookPdf(filePath, target) {
  const report = await inspectWorkbookPdf(filePath);
  if (report.pageCount < 1) {
    throw new WorkbookPdfAuditError(`PDF contains no pages: ${filePath}`);
  }

  let howToCount = 0;
  const observedSteps = [];

  for (const page of report.pages) {
    if (
      !approximately(page.width, A4_WIDTH_POINTS) ||
      !approximately(page.height, A4_HEIGHT_POINTS)
    ) {
      throw new WorkbookPdfAuditError(
        `PDF page is not A4 in ${filePath} on page ${page.number}: ` +
          `${page.width.toFixed(2)} × ${page.height.toFixed(2)} points.`,
      );
    }

    for (const item of page.items) {
      assertTextWithinPage(
        item,
        page.number,
        page.width,
        page.height,
        filePath,
      );
    }

    if (page.canonical.includes("HOWTOUSETHISWORKBOOK")) {
      howToCount += 1;
    }

    const footerMatch = page.text.match(/Page\s+(\d+)\s+of\s+(\d+)/i);
    const lessonCover =
      page.canonical.includes("READINGWORKBOOK") &&
      page.canonical.includes("LESSON");
    const coverPage = page.number === 1 || lessonCover;
    if (!coverPage && !footerMatch) {
      throw new WorkbookPdfAuditError(
        `Expected a page-number footer in ${filePath} on page ${page.number}.`,
      );
    }
    if (footerMatch) {
      const current = Number(footerMatch[1]);
      const total = Number(footerMatch[2]);
      if (current !== page.number || total !== report.pageCount) {
        throw new WorkbookPdfAuditError(
          `Incorrect page-number footer in ${filePath} on physical page ${page.number}: ` +
            `printed Page ${current} of ${total}, expected Page ${page.number} of ${report.pageCount}.`,
        );
      }
    }

    for (const section of SECTION_CHECKS) {
      if (footerMatch && page.canonical.includes(section.band)) {
        observedSteps.push(section.step);
        if (!page.headerCanonical.includes(section.name)) {
          throw new WorkbookPdfAuditError(
            `Section header mismatch in ${filePath} on page ${page.number}: ` +
              `Step ${section.step} does not have the expected running header.`,
          );
        }
      }
    }

    if (page.headerCanonical.includes("CONTINUED")) {
      throw new WorkbookPdfAuditError(
        `Running headers must use the standardized section name without “Continued” ` +
          `in ${filePath} on page ${page.number}.`,
      );
    }
  }

  if (howToCount !== 1) {
    throw new WorkbookPdfAuditError(
      `Expected exactly one “How to use this workbook” page in ${filePath}; found ${howToCount}.`,
    );
  }

  const expectedSteps = target.lessons.flatMap(() => [1, 2, 3, 4]);
  if (
    observedSteps.length !== expectedSteps.length ||
    observedSteps.some((step, index) => step !== expectedSteps[index])
  ) {
    throw new WorkbookPdfAuditError(
      `Section order mismatch in ${filePath}: observed ${observedSteps.join(", ") || "none"}; ` +
        `expected ${expectedSteps.join(", ")}.`,
    );
  }

  if (
    target.edition === "student" &&
    report.pages.some((page) =>
      page.canonical.includes("TEACHERGUIDANCE") ||
      page.canonical.includes("EXAMPLESTRUCTURERUBRIC"),
    )
  ) {
    throw new WorkbookPdfAuditError(
      `Teacher-only guidance leaked into the student PDF: ${filePath}.`,
    );
  }

  return report;
}
