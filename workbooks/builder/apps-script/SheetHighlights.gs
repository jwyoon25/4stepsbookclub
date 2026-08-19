/**
 * Showing the author which cell is wrong.
 *
 * Every validation message already names a tab, a row, and a column — the
 * content contract is written that way on purpose. Reading a message and then
 * hunting for row 47 of a tab forty columns wide is still work, so the cell it
 * names is filled, noted, and scrolled to.
 *
 * A mark is undone before the next one is made, and the marks are remembered in
 * document properties rather than searched for, because a colour is not
 * evidence: an author is free to fill a cell themselves, and clearing every
 * yellow cell on a tab would take that away from them.
 */

const FOURSTEPS_HIGHLIGHT_PROPERTY = "WORKBOOK_HIGHLIGHTS";
const FOURSTEPS_HIGHLIGHT_COLOUR = "#fde2dd";

/**
 * Mark the cell a validation message named, and go to it.
 *
 * `location` is `{ sheet, row, column, message }`. A problem belonging to a
 * whole tab arrives without a row, in which case the tab is opened and nothing
 * is filled: there is no one cell to blame.
 */
function highlightWorkbookCell(location) {
  clearWorkbookHighlights();
  if (!location || !location.sheet) {
    return null;
  }

  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = spreadsheet.getSheetByName(location.sheet);
  if (!sheet) {
    return null;
  }

  if (!location.row) {
    spreadsheet.setActiveSheet(sheet);
    return { sheet: sheet.getName() };
  }

  // A row-level problem has no column to blame, so the whole authored row is
  // marked: every column except the leading Status note the contract ignores.
  const range = location.column
    ? sheet.getRange(location.row, location.column)
    : sheet.getRange(location.row, 2, 1, Math.max(1, sheet.getLastColumn() - 1));

  range.setBackground(FOURSTEPS_HIGHLIGHT_COLOUR);
  if (location.message) {
    range.setNote(location.message);
  }
  spreadsheet.setActiveSheet(sheet);
  sheet.setActiveRange(range);

  PropertiesService.getDocumentProperties().setProperty(
    FOURSTEPS_HIGHLIGHT_PROPERTY,
    JSON.stringify([{ sheet: sheet.getName(), a1: range.getA1Notation() }]),
  );
  return { sheet: sheet.getName(), a1: range.getA1Notation() };
}

/** Undo whatever the last message marked, and forget it. */
function clearWorkbookHighlights() {
  const properties = PropertiesService.getDocumentProperties();
  const stored = properties.getProperty(FOURSTEPS_HIGHLIGHT_PROPERTY);
  if (!stored) {
    return;
  }

  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  JSON.parse(stored).forEach(function (mark) {
    const sheet = spreadsheet.getSheetByName(mark.sheet);
    if (!sheet) {
      return;
    }
    // A tab the author deleted and rebuilt can leave a mark that no longer
    // addresses anything, which is a reason to forget it rather than to fail.
    try {
      sheet.getRange(mark.a1).setBackground(null).clearNote();
    } catch (error) {
      // The range is gone; there is nothing left to clear.
    }
  });

  properties.deleteProperty(FOURSTEPS_HIGHLIGHT_PROPERTY);
}
