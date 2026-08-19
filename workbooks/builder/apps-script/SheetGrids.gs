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
 * Read the workbook's tabs as grids of cell values.
 *
 * `wanted` is the list of tab names to read, and it comes from the browser
 * because the browser is where the contract lives. Naming them here instead
 * would be a second copy of something that already exists, free to drift; this
 * way the script still knows nothing about what a workbook is. Called with
 * nothing, it reads every tab, which is what the Phase 0 dialog does.
 *
 * Reading only what is asked for is worth about half a second per tab skipped.
 * A tutor's drafts, notes, and scratch work stay in the file and go unread
 * rather than being fetched and thrown away, and a tab that should be there and
 * is not simply does not appear, which is the failure the contract already
 * reports by name.
 *
 * Returns `{ spreadsheetName, grids, tabs, cells, milliseconds }`. The timings
 * come with the cells because this is the wait an author hits most: it happens
 * after every edit, and it has measured between three and eleven seconds for a
 * one-lesson workbook. Which part is the script and which is the trip to the
 * browser is not something to infer from outside, so it is reported from
 * inside.
 */
function readWorkbookGrids(wanted) {
  const startedAt = new Date().getTime();
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  SpreadsheetApp.flush();
  const flushedAt = new Date().getTime();

  const sheets =
    wanted && wanted.length > 0
      ? wanted
          .map(function (name) {
            return spreadsheet.getSheetByName(name);
          })
          .filter(Boolean)
      : spreadsheet.getSheets();

  const grids = {};
  let cells = 0;
  sheets.forEach(function (sheet) {
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
