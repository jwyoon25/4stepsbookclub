/**
 * The 4steps menu, and the window it opens.
 *
 * Three items, all of which are the same window opened with a different job to
 * do: check the workbook, look at it, or build every PDF it owes. They share a
 * window because the workbook only exists in one place — the author's browser,
 * where the Typst compiler and the content contract both run. Apps Script's
 * part is to hand over the cells and to receive what comes back, which is why
 * `SheetGrids.gs` and `WorkbookExport.gs` are the only script this needs.
 *
 * The dialog is modeless so the Sheet stays editable beside the preview, and it
 * has to stay open: it is the preview window's only route to Google.
 */

const FOURSTEPS_BUILDER_DEFAULT_PREVIEW_URL =
  "http://localhost:8787/preview.html";

/** Report which cells are wrong without building anything. */
function validateWorkbook() {
  openWorkbookBuilder_("validate", "Validate workbook");
}

/** Open the workbook the author is editing and compile it. */
function openWorkbookPreview() {
  openWorkbookBuilder_("preview", "Workbook preview");
}

/**
 * Build every PDF the workbook owes and file them in Drive.
 *
 * "Approved" is the author's judgement, made by looking at the preview before
 * choosing this. Nothing in the Sheet records it: approval mechanics are
 * explicitly unsettled in CONTENT-WORKFLOW-DECISIONS.md, and the Status column
 * on every tab is a note to the people working on the book, not an input.
 */
function createAllApprovedPdfs() {
  openWorkbookBuilder_("export", "Create all approved PDFs");
}

function openWorkbookBuilder_(intent, title) {
  const template = HtmlService.createTemplateFromFile("WorkbookBuilderDialog");
  template.previewUrl = workbookPreviewUrl_();
  template.intent = intent;
  SpreadsheetApp.getUi().showModelessDialog(
    template.evaluate().setWidth(420).setHeight(480),
    "4steps · " + title,
  );
}

/**
 * Where the preview window lives.
 *
 * The bundle is static files. Which host serves them is still open in
 * BUILDER-ARCHITECTURE-DECISION.md, so the address is a script property and the
 * default is the local gate server the runbook uses.
 */
function workbookPreviewUrl_() {
  const configured = (
    PropertiesService.getScriptProperties().getProperty("PREVIEW_URL") || ""
  ).trim();
  return configured || FOURSTEPS_BUILDER_DEFAULT_PREVIEW_URL;
}
