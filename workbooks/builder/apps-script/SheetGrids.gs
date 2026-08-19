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
 * Returns `{ spreadsheetName, grids }`, where `grids` maps a tab name to its
 * rows. Extra tabs — drafts, notes, scratch work — are included and ignored by
 * the contract, so a tutor can keep whatever else they need in the file.
 */
function readWorkbookGrids() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  SpreadsheetApp.flush();

  const grids = {};
  spreadsheet.getSheets().forEach(function (sheet) {
    grids[sheet.getName()] = sheet
      .getDataRange()
      .getValues()
      .map(function (row) {
        return row.map(transferableCellValue_);
      });
  });

  return { spreadsheetName: spreadsheet.getName(), grids };
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
