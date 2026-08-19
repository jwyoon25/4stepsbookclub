// ---------------------------------------------------------------------------
// Comparing two renderings of the same workbook.
//
// The browser compiler is only allowed to replace the native renderer if it
// produces the same document, so "visual parity" has to be a measurement rather
// than an impression. Two comparisons are available:
//
//   comparePdfDocuments  every page's text runs, their positions, and the
//                        response rules, read back out of the finished PDFs
//   comparePagePixels    the rasterized pages, channel by channel
//
// The first works on any two PDFs, including one produced in a real browser and
// posted back for checking. The second needs both renderers on hand and is the
// stronger claim: identical pixels leave nothing to interpret.
// ---------------------------------------------------------------------------

import { inflateSync } from "node:zlib";

import { inspectWorkbookPdf } from "./pdf-audit.mjs";

// Positions are compared exactly; the tolerance exists only so that a rounding
// difference in how a number is written cannot masquerade as a layout change.
const POSITION_TOLERANCE_POINTS = 0.001;

const PNG_SIGNATURE_BYTES = 8;
const PNG_COLOR_TYPE_RGB = 2;
const PNG_COLOR_TYPE_RGBA = 6;

export class RenderParityError extends Error {
  constructor(message) {
    super(message);
    this.name = "RenderParityError";
  }
}

function summarize(differences) {
  if (differences.length === 0) {
    return "identical";
  }
  const [first] = differences;
  return differences.length === 1
    ? first
    : `${first} (and ${differences.length - 1} more)`;
}

/**
 * Compare the text and ruled lines of two rendered PDFs.
 *
 * `left` is the reference — in practice the native renderer's output.
 */
export async function comparePdfDocuments(leftPath, rightPath) {
  const [left, right] = await Promise.all([
    inspectWorkbookPdf(leftPath),
    inspectWorkbookPdf(rightPath),
  ]);

  const differences = [];
  let textItems = 0;
  let ruledLines = 0;
  let worstOffsetPoints = 0;

  if (left.pageCount !== right.pageCount) {
    differences.push(
      `page count ${left.pageCount} versus ${right.pageCount}`,
    );
  }

  const pageCount = Math.min(left.pageCount, right.pageCount);
  for (let index = 0; index < pageCount; index += 1) {
    const leftPage = left.pages[index];
    const rightPage = right.pages[index];
    const page = index + 1;

    if (
      leftPage.width !== rightPage.width ||
      leftPage.height !== rightPage.height
    ) {
      differences.push(
        `page ${page} measures ${leftPage.width}×${leftPage.height} versus ` +
          `${rightPage.width}×${rightPage.height}`,
      );
    }

    if (leftPage.items.length !== rightPage.items.length) {
      differences.push(
        `page ${page} has ${leftPage.items.length} text runs versus ` +
          `${rightPage.items.length}`,
      );
    }

    const items = Math.min(leftPage.items.length, rightPage.items.length);
    for (let item = 0; item < items; item += 1) {
      const leftItem = leftPage.items[item];
      const rightItem = rightPage.items[item];
      textItems += 1;

      if (leftItem.str !== rightItem.str) {
        differences.push(
          `page ${page} text run ${item} reads ${JSON.stringify(rightItem.str)} ` +
            `instead of ${JSON.stringify(leftItem.str)}`,
        );
        continue;
      }

      const offset = Math.max(
        Math.abs(leftItem.transform[4] - rightItem.transform[4]),
        Math.abs(leftItem.transform[5] - rightItem.transform[5]),
        Math.abs(leftItem.width - rightItem.width),
      );
      worstOffsetPoints = Math.max(worstOffsetPoints, offset);
      if (offset > POSITION_TOLERANCE_POINTS) {
        differences.push(
          `page ${page} moves ${JSON.stringify(leftItem.str.slice(0, 40))} by ` +
            `${offset.toFixed(3)} points`,
        );
      }
    }

    if (leftPage.ruledLines.length !== rightPage.ruledLines.length) {
      differences.push(
        `page ${page} has ${leftPage.ruledLines.length} response rules versus ` +
          `${rightPage.ruledLines.length}`,
      );
    }

    const rules = Math.min(
      leftPage.ruledLines.length,
      rightPage.ruledLines.length,
    );
    for (let rule = 0; rule < rules; rule += 1) {
      ruledLines += 1;
      const offset = Math.max(
        Math.abs(leftPage.ruledLines[rule].pageY - rightPage.ruledLines[rule].pageY),
        Math.abs(leftPage.ruledLines[rule].width - rightPage.ruledLines[rule].width),
      );
      worstOffsetPoints = Math.max(worstOffsetPoints, offset);
      if (offset > POSITION_TOLERANCE_POINTS) {
        differences.push(
          `page ${page} moves a response rule by ${offset.toFixed(3)} points`,
        );
      }
    }
  }

  return {
    identical: differences.length === 0,
    pageCount: left.pageCount,
    textItems,
    ruledLines,
    worstOffsetPoints,
    differences,
    summary: summarize(differences),
  };
}

/**
 * Decode a non-interlaced 8-bit PNG into raw channels.
 *
 * Both renderers write exactly this kind of PNG, so a full decoder would be
 * dead weight: this reads the header, inflates the image data, and undoes the
 * per-row filters.
 */
export function decodePng(source) {
  const buffer = Buffer.isBuffer(source)
    ? source
    : Buffer.from(source.buffer, source.byteOffset, source.byteLength);
  let offset = PNG_SIGNATURE_BYTES;
  let width = 0;
  let height = 0;
  let channels = 0;
  const imageData = [];

  while (offset + 8 <= buffer.length) {
    const length = buffer.readUInt32BE(offset);
    const type = buffer.toString("ascii", offset + 4, offset + 8);
    const data = buffer.subarray(offset + 8, offset + 8 + length);

    if (type === "IHDR") {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      const bitDepth = data[8];
      const colorType = data[9];
      const interlace = data[12];
      if (bitDepth !== 8) {
        throw new RenderParityError(`Unsupported PNG bit depth: ${bitDepth}.`);
      }
      if (colorType !== PNG_COLOR_TYPE_RGB && colorType !== PNG_COLOR_TYPE_RGBA) {
        throw new RenderParityError(`Unsupported PNG colour type: ${colorType}.`);
      }
      if (interlace !== 0) {
        throw new RenderParityError("Interlaced PNGs are not supported.");
      }
      channels = colorType === PNG_COLOR_TYPE_RGBA ? 4 : 3;
    } else if (type === "IDAT") {
      imageData.push(Buffer.from(data));
    } else if (type === "IEND") {
      break;
    }

    offset += 12 + length;
  }

  const stride = width * channels;
  const filtered = inflateSync(Buffer.concat(imageData));
  const pixels = Buffer.alloc(height * stride);

  for (let row = 0; row < height; row += 1) {
    const filter = filtered[row * (stride + 1)];
    const filteredRow = filtered.subarray(
      row * (stride + 1) + 1,
      row * (stride + 1) + 1 + stride,
    );
    const target = pixels.subarray(row * stride, (row + 1) * stride);
    const above = row > 0 ? pixels.subarray((row - 1) * stride, row * stride) : null;

    for (let index = 0; index < stride; index += 1) {
      const left = index >= channels ? target[index - channels] : 0;
      const up = above ? above[index] : 0;
      const upLeft = above && index >= channels ? above[index - channels] : 0;
      const value = filteredRow[index];

      switch (filter) {
        case 0:
          target[index] = value;
          break;
        case 1:
          target[index] = value + left;
          break;
        case 2:
          target[index] = value + up;
          break;
        case 3:
          target[index] = value + ((left + up) >> 1);
          break;
        case 4: {
          const estimate = left + up - upLeft;
          const toLeft = Math.abs(estimate - left);
          const toUp = Math.abs(estimate - up);
          const toUpLeft = Math.abs(estimate - upLeft);
          const nearest =
            toLeft <= toUp && toLeft <= toUpLeft ? left : toUp <= toUpLeft ? up : upLeft;
          target[index] = value + nearest;
          break;
        }
        default:
          throw new RenderParityError(`Unknown PNG row filter: ${filter}.`);
      }
    }
  }

  return { width, height, channels, pixels };
}

/**
 * Compare two sets of rendered pages channel by channel.
 *
 * Both arguments are arrays of PNG bytes, one entry per page, in page order.
 */
export function comparePagePixels(leftPages, rightPages) {
  const differences = [];
  if (leftPages.length !== rightPages.length) {
    differences.push(
      `page count ${leftPages.length} versus ${rightPages.length}`,
    );
  }

  let totalChannels = 0;
  let differingChannels = 0;
  let worstChannelDelta = 0;

  const pageCount = Math.min(leftPages.length, rightPages.length);
  for (let index = 0; index < pageCount; index += 1) {
    const left = decodePng(leftPages[index]);
    const right = decodePng(rightPages[index]);
    const page = index + 1;

    if (
      left.width !== right.width ||
      left.height !== right.height ||
      left.channels !== right.channels
    ) {
      differences.push(
        `page ${page} renders ${left.width}×${left.height} versus ` +
          `${right.width}×${right.height}`,
      );
      continue;
    }

    let differingOnPage = 0;
    for (let channel = 0; channel < left.pixels.length; channel += 1) {
      totalChannels += 1;
      const delta = Math.abs(left.pixels[channel] - right.pixels[channel]);
      if (delta > 0) {
        differingChannels += 1;
        differingOnPage += 1;
        worstChannelDelta = Math.max(worstChannelDelta, delta);
      }
    }

    if (differingOnPage > 0) {
      differences.push(
        `page ${page} differs in ${differingOnPage} of ${left.pixels.length} channels`,
      );
    }
  }

  return {
    identical: differences.length === 0,
    pageCount,
    totalChannels,
    differingChannels,
    worstChannelDelta,
    differences,
    summary: summarize(differences),
  };
}
