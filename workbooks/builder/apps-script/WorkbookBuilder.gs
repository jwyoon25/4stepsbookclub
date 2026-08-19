/**
 * The 4steps menu, and the window it opens.
 *
 * The builder actions all use the same window opened with a different job to
 * do: set up, check the workbook, look at it, or build every PDF it owes. They
 * share a window because the workbook only exists in one place — the author's browser,
 * where the Typst compiler and the content contract both run. Apps Script's
 * part is to hand over the cells and to receive what comes back, which is why
 * `SheetGrids.gs` and `WorkbookExport.gs` are the only script this needs.
 *
 * The dialog is modeless so the Sheet stays editable beside the preview, and it
 * has to stay open: it is the preview window's only route to Google.
 */

// Production copies work immediately after the one-time Google authorization.
// Developers can override this with PREVIEW_URL for the local browser gate.
const FOURSTEPS_BUILDER_DEFAULT_PREVIEW_URL =
  "https://4steps-workbook-builder.pages.dev/preview";

/**
 * Connect a copied workbook to the builder.
 *
 * The first click deliberately touches the current Sheet and its Drive file:
 * Google can then show the one-time consent screen for the services the
 * workbook needs. The consent itself must remain a user action, but the setup
 * path and production preview address are automatic from this point on.
 */
function setupWorkbook() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  const file = DriveApp.getFileById(spreadsheet.getId());
  const parents = file.getParents();
  const parentName = parents.hasNext() ? parents.next().getName() : "My Drive";
  const properties = PropertiesService.getScriptProperties();
  const configured = (properties.getProperty("PREVIEW_URL") || "").trim();

  if (!configured) {
    properties.setProperty(
      "PREVIEW_URL",
      FOURSTEPS_BUILDER_DEFAULT_PREVIEW_URL,
    );
  }

  const ui = SpreadsheetApp.getUi();
  ui.alert(
    "4steps workbook is ready",
    [
      `Workbook: ${spreadsheet.getName()}`,
      `Drive folder: ${parentName}`,
      `Preview: ${workbookPreviewUrl_()}`,
      "",
      "Next: use 4steps → Validate workbook, then open the preview.",
    ].join("\n"),
    ui.ButtonSet.OK,
  );
}

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
 * The bundle is static files hosted on Cloudflare Pages for production. The
 * script property remains an override for local development and future hosts.
 */
function workbookPreviewUrl_() {
  const configured = (
    PropertiesService.getScriptProperties().getProperty("PREVIEW_URL") || ""
  ).trim();
  return configured || FOURSTEPS_BUILDER_DEFAULT_PREVIEW_URL;
}
