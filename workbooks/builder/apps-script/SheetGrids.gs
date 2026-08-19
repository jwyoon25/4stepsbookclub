/**
 * The Sheet adapter.
 *
 * Apps Script's only job in the authoring loop is to hand the preview window
 * what the tutor has typed. It does not know what a workbook is: it reads every
 * tab as a grid of cells and sends them on. Which tabs matter, what their
 * columns mean, and whether the content is valid are all decided by
 * `builder/browser/sheet-contract.mjs`, which the preview window runs.
 *
 * Keeping the knowledge on one side of the wire is deliberate. Apps Script
 * cannot import the contract, so anything it believed about the workbook would
 * be a second copy free to drift from the first.
 */

/**
 * Read every tab of the active spreadsheet as a grid of cell values.
 *
 * Returns `{ spreadsheetName, grids, tabs, cells, milliseconds }`, where `grids`
 * maps a tab name to its rows. Extra tabs — drafts, notes, scratch work — are
 * included and ignored by the contract, so a tutor can keep whatever else they
 * need in the file.
 *
 * The timings come back with the cells because this is the wait an author hits
 * most: it happens on every refresh, and it has measured between three and
 * eleven seconds for a one-lesson workbook. Which part of that is the script
 * and which is the trip to the browser is not something to infer from the
 * outside, so it is reported from the inside.
 */
function readWorkbookGrids() {
  const startedAt = new Date().getTime();
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  SpreadsheetApp.flush();
  const flushedAt = new Date().getTime();

  const grids = {};
  let cells = 0;
  spreadsheet.getSheets().forEach(function (sheet) {
    const rows = sheet
      .getDataRange()
      .getValues()
      .map(function (row) {
        return row.map(transferableCellValue_);
      });
    cells += rows.length * (rows.length > 0 ? rows[0].length : 0);
    grids[sheet.getName()] = rows;
  });
  const readAt = new Date().getTime();

  return {
    spreadsheetName: spreadsheet.getName(),
    grids: grids,
    tabs: Object.keys(grids).length,
    cells: cells,
    milliseconds: {
      flush: flushedAt - startedAt,
      read: readAt - flushedAt,
      total: readAt - startedAt,
    },
  };
}

/**
 * Reduce one cell to something that survives the trip to the browser.
 *
 * Everything a tutor types arrives as a string, a number, or a boolean. A cell
 * Google decided was a date arrives as a Date, which does not survive
 * `google.script.run` intact — and should not be quietly turned into text
 * either, because a chapter range typed as 9-13 becoming a date is a mistake
 * the author needs told. Wrapping it keeps it a non-text value, so the contract
 * rejects it by name, exactly as the spreadsheet importer does.
 */
function transferableCellValue_(value) {
  if (value instanceof Date) {
    return { date: value.toISOString() };
  }
  return value;
}
