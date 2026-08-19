/**
 * The Drive half of the browser export.
 *
 * The author's browser compiles every PDF a workbook owes — a lesson and a
 * complete book, in student and teacher editions — and this file puts them
 * where the 4steps convention says they go. It receives ZIP archives rather
 * than files: the Phase 0 gate measured one 0.47 MB PDF taking 7.78 seconds
 * through `google.script.run`, so a twenty-six file book sent one call at a
 * time would cost an author roughly three minutes of waiting.
 *
 * The build folder is `Code.gs`'s, deliberately. Both renderers write to
 * `<the Sheet's folder>/4steps PDF Builds/<book title>/<timestamp>/`, and a
 * second implementation of that convention here is a second thing to keep in
 * step with the first.
 *
 * No new OAuth scopes: `Code.gs` already asks for Drive, and unpacking an
 * archive is the same `Utilities.unzip` its renderer path has always used.
 */

/**
 * Begin an export and return the folder its PDFs belong in.
 *
 * The folder is made once, before any bytes move, so that every archive of one
 * export lands together and a failure halfway through leaves a folder holding
 * what did arrive rather than scattering files across two timestamps.
 */
function startWorkbookExport() {
  if (typeof createBuildFolder_ !== "function") {
    throw new Error(
      "Code.gs is missing from this Apps Script project, so the Drive build " +
        "folder convention is not available. Add this repository's Code.gs.",
    );
  }

  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  const folder = createBuildFolder_(spreadsheet);
  return {
    folderId: folder.getId(),
    folderName: folder.getName(),
    folderUrl: folder.getUrl(),
  };
}

/**
 * Unpack one archive of finished PDFs into an export's folder.
 *
 * The timings come back with the files because the transfer is the slowest step
 * in the system by two orders of magnitude and nobody has yet established which
 * half of it is slow. `milliseconds` is what this script spent; the caller knows
 * the wall time, and the difference is what the channel itself costs.
 */
function saveWorkbookArchive(request) {
  if (!request || !request.base64 || !request.folderId) {
    throw new Error("The preview window sent no archive to save.");
  }

  const receivedAt = new Date().getTime();
  const archive = Utilities.newBlob(
    Utilities.base64Decode(request.base64),
    "application/zip",
    "workbook-pdfs.zip",
  );
  const decodedAt = new Date().getTime();

  const pdfs = Utilities.unzip(archive).filter(function (blob) {
    return blob.getName().toLowerCase().slice(-4) === ".pdf";
  });
  if (pdfs.length === 0) {
    throw new Error("The archive contained no PDF files.");
  }
  const unzippedAt = new Date().getTime();

  const folder = DriveApp.getFolderById(request.folderId);
  const files = pdfs.map(function (blob) {
    const file = folder.createFile(blob);
    return { name: file.getName(), url: file.getUrl() };
  });

  return {
    files: files,
    archiveBytes: archive.getBytes().length,
    milliseconds: {
      decode: decodedAt - receivedAt,
      unzip: unzippedAt - decodedAt,
      write: new Date().getTime() - unzippedAt,
      total: new Date().getTime() - receivedAt,
    },
  };
}
