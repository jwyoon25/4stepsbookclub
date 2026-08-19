// ---------------------------------------------------------------------------
// How finished PDFs get to Google Drive.
//
// The Phase 0 gate measured the answer this file is built around: 7.78 seconds
// for one 0.47 MB PDF through `google.script.run`, against 168 milliseconds to
// compile it. Sending a twelve-lesson book's twenty-six files that way is about
// three minutes of an author's afternoon, so they travel as ZIP archives
// instead — one call carrying many PDFs, unpacked on the Apps Script side by
// `Utilities.unzip`, which the native renderer's Drive path has used since
// before any of this existed.
//
// Two reasons the archives are compressed and not merely bundled. Workbook PDFs
// deflate to about 75% of their size, which is real money on a channel this
// slow; and `Utilities.unzip` already reads the renderer's DEFLATE archives, so
// the format is proven rather than assumed.
//
// Like the rest of `builder/browser/`, this imports nothing. `CompressionStream`
// is the browser's own deflate and Node's as well, so the same archive writer
// runs in the preview window and under test.
// ---------------------------------------------------------------------------

// How much of an archive one `google.script.run` call carries. The payload is
// base64 on the wire, so the real transfer is a third larger again.
//
// The gate proved 0.47 MB of PDF — 0.63 MB base64 — arrives intact, and nothing
// has established the ceiling above that. This is deliberately a modest step up
// from the proven figure rather than the largest archive that might work: the
// suspected cost is the number of calls rather than their size, and a
// twelve-lesson book fits in two calls at this budget instead of twenty-six.
// `createPdfArchives` halves it and repacks if a host turns out to disagree.
export const DEFAULT_MAX_ARCHIVE_BYTES = 2 * 1024 * 1024;

// Below this an archive is one PDF per call, which is the slow path the
// batching exists to avoid; halving further would buy nothing.
export const MINIMUM_MAX_ARCHIVE_BYTES = 256 * 1024;

export class PdfArchiveError extends Error {
  constructor(message, options) {
    super(message, options);
    this.name = "PdfArchiveError";
  }
}

const LOCAL_HEADER_SIGNATURE = 0x04034b50;
const CENTRAL_HEADER_SIGNATURE = 0x02014b50;
const END_OF_DIRECTORY_SIGNATURE = 0x06054b50;
const DEFLATE_METHOD = 8;
// Version 2.0 is what "deflated, no encryption" requires, and the flag marks
// entry names as UTF-8. Workbook file names are ASCII today, but a book titled
// in Hangul would slug to something that is not.
const REQUIRED_ZIP_VERSION = 20;
const UTF8_NAME_FLAG = 0x800;

const CRC32_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let index = 0; index < 256; index += 1) {
    let value = index;
    for (let bit = 0; bit < 8; bit += 1) {
      value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
    }
    table[index] = value >>> 0;
  }
  return table;
})();

function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc = CRC32_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

/**
 * The archive's own timestamp, in the format ZIP has used since MS-DOS.
 *
 * Drive stamps the files it creates with the time it creates them, so this only
 * shows when someone downloads an archive rather than letting Apps Script
 * unpack it. Recording the real time is still better than the 1980 every
 * fixed-timestamp writer produces.
 */
function dosDateTime(date) {
  const year = Math.max(1980, date.getFullYear());
  return {
    time:
      (date.getHours() << 11) |
      (date.getMinutes() << 5) |
      (Math.floor(date.getSeconds() / 2) & 0x1f),
    date: ((year - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate(),
  };
}

async function deflateRaw(bytes) {
  const compressed = new Blob([bytes])
    .stream()
    .pipeThrough(new CompressionStream("deflate-raw"));
  return new Uint8Array(await new Response(compressed).arrayBuffer());
}

/**
 * Compress every PDF once.
 *
 * Packing decides how many archives there are by how large the compressed
 * entries turn out to be, and a retry at a smaller budget repacks the same
 * entries rather than compressing them again.
 */
export async function compressPdfEntries(files) {
  return Promise.all(
    files.map(async ({ name, bytes }) => {
      if (!name || !(bytes instanceof Uint8Array)) {
        throw new PdfArchiveError(
          `Every archive entry needs a name and PDF bytes; received ${JSON.stringify(name)}.`,
        );
      }
      const deflated = await deflateRaw(bytes);
      return {
        name,
        nameBytes: new TextEncoder().encode(name),
        crc: crc32(bytes),
        rawBytes: bytes.length,
        deflated,
      };
    }),
  );
}

function writeArchive(entries, now = new Date()) {
  const { time, date } = dosDateTime(now);
  const localHeaderBytes = entries.reduce(
    (total, entry) => total + 30 + entry.nameBytes.length + entry.deflated.length,
    0,
  );
  const directoryBytes = entries.reduce(
    (total, entry) => total + 46 + entry.nameBytes.length,
    0,
  );

  const archive = new Uint8Array(localHeaderBytes + directoryBytes + 22);
  const view = new DataView(archive.buffer);
  let offset = 0;
  const offsets = [];

  for (const entry of entries) {
    offsets.push(offset);
    view.setUint32(offset, LOCAL_HEADER_SIGNATURE, true);
    view.setUint16(offset + 4, REQUIRED_ZIP_VERSION, true);
    view.setUint16(offset + 6, UTF8_NAME_FLAG, true);
    view.setUint16(offset + 8, DEFLATE_METHOD, true);
    view.setUint16(offset + 10, time, true);
    view.setUint16(offset + 12, date, true);
    view.setUint32(offset + 14, entry.crc, true);
    view.setUint32(offset + 18, entry.deflated.length, true);
    view.setUint32(offset + 22, entry.rawBytes, true);
    view.setUint16(offset + 26, entry.nameBytes.length, true);
    view.setUint16(offset + 28, 0, true);
    archive.set(entry.nameBytes, offset + 30);
    archive.set(entry.deflated, offset + 30 + entry.nameBytes.length);
    offset += 30 + entry.nameBytes.length + entry.deflated.length;
  }

  const directoryStart = offset;
  for (const [index, entry] of entries.entries()) {
    view.setUint32(offset, CENTRAL_HEADER_SIGNATURE, true);
    view.setUint16(offset + 4, REQUIRED_ZIP_VERSION, true);
    view.setUint16(offset + 6, REQUIRED_ZIP_VERSION, true);
    view.setUint16(offset + 8, UTF8_NAME_FLAG, true);
    view.setUint16(offset + 10, DEFLATE_METHOD, true);
    view.setUint16(offset + 12, time, true);
    view.setUint16(offset + 14, date, true);
    view.setUint32(offset + 16, entry.crc, true);
    view.setUint32(offset + 20, entry.deflated.length, true);
    view.setUint32(offset + 24, entry.rawBytes, true);
    view.setUint16(offset + 28, entry.nameBytes.length, true);
    view.setUint32(offset + 42, offsets[index], true);
    archive.set(entry.nameBytes, offset + 46);
    offset += 46 + entry.nameBytes.length;
  }

  view.setUint32(offset, END_OF_DIRECTORY_SIGNATURE, true);
  view.setUint16(offset + 8, entries.length, true);
  view.setUint16(offset + 10, entries.length, true);
  view.setUint32(offset + 12, offset - directoryStart, true);
  view.setUint32(offset + 16, directoryStart, true);
  return archive;
}

/**
 * Group compressed entries into archives no larger than the budget.
 *
 * A PDF larger than the budget on its own still gets an archive, because the
 * alternative is refusing to export a workbook that compiled perfectly well.
 * The budget decides how many calls an export costs, never which files it
 * contains.
 *
 * `limit` stops after that many archives. A sender that may have its budget
 * changed under it wants only the next call's worth, because everything after
 * it would have to be packed again anyway.
 */
export function packPdfArchives(
  entries,
  { maxArchiveBytes = DEFAULT_MAX_ARCHIVE_BYTES, limit = Infinity, now } = {},
) {
  const batches = [];
  let batch = [];
  let batchBytes = 0;

  for (const entry of entries) {
    if (batch.length > 0 && batchBytes + entry.deflated.length > maxArchiveBytes) {
      batches.push(batch);
      if (batches.length >= limit) {
        batch = [];
        break;
      }
      batch = [];
      batchBytes = 0;
    }
    batch.push(entry);
    batchBytes += entry.deflated.length;
  }
  if (batch.length > 0 && batches.length < limit) {
    batches.push(batch);
  }

  return batches.map((archiveEntries) => ({
    bytes: writeArchive(archiveEntries, now),
    names: archiveEntries.map(({ name }) => name),
  }));
}

/** Compress a set of PDFs and pack them into transferable archives. */
export async function createPdfArchives(files, options = {}) {
  return packPdfArchives(await compressPdfEntries(files), options);
}
