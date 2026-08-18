import { readFile } from "node:fs/promises";

import { getDocument, OPS } from "pdfjs-dist/legacy/build/pdf.mjs";

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

function multiplyTransforms(left, right) {
  const [a1, b1, c1, d1, e1, f1] = left;
  const [a2, b2, c2, d2, e2, f2] = right;
  return [
    a1 * a2 + c1 * b2,
    b1 * a2 + d1 * b2,
    a1 * c2 + c1 * d2,
    b1 * c2 + d1 * d2,
    a1 * e2 + c1 * f2 + e1,
    b1 * e2 + d1 * f2 + f1,
  ];
}

function inspectRuledLines(operatorList) {
  const stack = [];
  let state = {
    transform: [1, 0, 0, 1, 0, 0],
    strokeColor: "",
  };
  const lines = [];

  for (let index = 0; index < operatorList.fnArray.length; index += 1) {
    const operation = operatorList.fnArray[index];
    const argumentsList = operatorList.argsArray[index];

    if (operation === OPS.save) {
      stack.push({
        transform: [...state.transform],
        strokeColor: state.strokeColor,
      });
    } else if (operation === OPS.restore) {
      state = stack.pop() ?? state;
    } else if (operation === OPS.transform) {
      state.transform = multiplyTransforms(state.transform, argumentsList);
    } else if (operation === OPS.setStrokeRGBColor) {
      state.strokeColor = String(argumentsList[0]).toLowerCase();
    } else if (operation === OPS.constructPath) {
      const bounds = argumentsList?.[2];
      if (!bounds) {
        continue;
      }

      const width = Math.abs(Number(bounds[2]) - Number(bounds[0]));
      const height = Math.abs(Number(bounds[3]) - Number(bounds[1]));
      if (
        state.strokeColor === "#c6d0c8" &&
        width >= 400 &&
        height <= 0.1
      ) {
        lines.push({
          width,
          pageY: state.transform[5],
        });
      }
    }
  }

  return lines.sort((left, right) => right.pageY - left.pageY);
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
      const operatorList = await page.getOperatorList();
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
        ruledLines: inspectRuledLines(operatorList),
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
    for (const line of page.ruledLines) {
      if (
        line.pageY < -BOUNDS_TOLERANCE_POINTS ||
        line.pageY > page.height + BOUNDS_TOLERANCE_POINTS
      ) {
        throw new WorkbookPdfAuditError(
          `A response rule leaves the page bounds in ${filePath} on page ${page.number}.`,
        );
      }
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
