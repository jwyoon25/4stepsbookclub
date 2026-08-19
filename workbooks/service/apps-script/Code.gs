const FOURSTEPS_MENU_TITLE = "4steps";
const FOURSTEPS_OUTPUT_FOLDER = "4steps PDF Builds";
const FOURSTEPS_XLSX_MIME =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

function onOpen() {
  const menu = SpreadsheetApp.getUi().createMenu(FOURSTEPS_MENU_TITLE);

  // The builder compiles in the author's browser and previews the real PDF
  // before anything is filed. Its items appear only while
  // builder/apps-script/WorkbookBuilder.gs is in the project, so a Sheet that
  // has not been connected to it shows a menu of what it can actually do
  // rather than builder items that fail when clicked.
  if (typeof openWorkbookPreview === "function") {
    menu
      .addItem("Set up this workbook", "setupWorkbook")
      .addSeparator()
      .addItem("Validate workbook", "validateWorkbook")
      .addItem("Open preview", "openWorkbookPreview")
      .addItem("Create all approved PDFs", "createAllApprovedPdfs")
      .addSeparator();
  }

  // The hosted renderer stays available: it needs no browser support and no
  // static host, which is what makes it the recovery path when the builder
  // cannot run.
  menu.addItem("Create PDFs with the hosted renderer", "createWorkbookPdfs");

  // The browser-compiler gate is a temporary spike. The item appears only while
  // builder/apps-script/Phase0.gs is in the project, so removing that file after
  // the gate removes the menu entry with it.
  if (typeof openPhase0Gate === "function") {
    menu.addItem("Browser compiler gate (Phase 0)", "openPhase0Gate");
  }

  menu.addToUi();
}

function createWorkbookPdfs() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  const ui = SpreadsheetApp.getUi();
  spreadsheet.toast("Validating and rendering the workbook…", "4steps", -1);

  try {
    const config = getRendererConfig_();
    SpreadsheetApp.flush();
    const workbookBlob = exportActiveSpreadsheet_();
    const response = UrlFetchApp.fetch(`${config.url}/render`, {
      method: "post",
      contentType: FOURSTEPS_XLSX_MIME,
      payload: workbookBlob.getBytes(),
      headers: { Authorization: `Bearer ${config.token}` },
      muteHttpExceptions: true,
    });

    if (response.getResponseCode() !== 200) {
      throw new Error(rendererErrorMessage_(response));
    }

    const pdfBlobs = Utilities.unzip(response.getBlob()).filter((blob) =>
      blob.getName().toLowerCase().endsWith(".pdf"),
    );
    if (pdfBlobs.length === 0) {
      throw new Error("The renderer returned no PDF files.");
    }

    const outputFolder = createBuildFolder_(spreadsheet);
    const files = pdfBlobs.map((blob) => outputFolder.createFile(blob));
    spreadsheet.toast(
      `Created ${files.length} PDFs in Google Drive.`,
      "4steps",
      8,
    );
    showBuildResult_(ui, outputFolder, files);
  } catch (error) {
    spreadsheet.toast("PDF generation failed.", "4steps", 8);
    ui.alert(
      "PDF generation failed",
      error && error.message ? error.message : String(error),
      ui.ButtonSet.OK,
    );
  }
}

function getRendererConfig_() {
  const properties = PropertiesService.getScriptProperties();
  const url = (properties.getProperty("RENDERER_URL") || "")
    .trim()
    .replace(/\/+$/, "");
  const token = (properties.getProperty("RENDERER_TOKEN") || "").trim();
  if (!url || !token) {
    throw new Error(
      "This template has not been connected to the 4steps PDF renderer yet.",
    );
  }
  return { url, token };
}

function exportActiveSpreadsheet_() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  const exportUrl =
    `https://docs.google.com/spreadsheets/d/${spreadsheet.getId()}` +
    "/export?format=xlsx";
  const response = UrlFetchApp.fetch(exportUrl, {
    headers: { Authorization: `Bearer ${ScriptApp.getOAuthToken()}` },
    muteHttpExceptions: true,
  });
  if (response.getResponseCode() !== 200) {
    throw new Error(
      `Google Sheets export failed with status ${response.getResponseCode()}.`,
    );
  }
  return response.getBlob().setName(`${spreadsheet.getName()}.xlsx`);
}

function createBuildFolder_(spreadsheet) {
  const spreadsheetFile = DriveApp.getFileById(spreadsheet.getId());
  const parents = spreadsheetFile.getParents();
  const parent = parents.hasNext() ? parents.next() : DriveApp.getRootFolder();
  const buildsRoot = getOrCreateFolder_(parent, FOURSTEPS_OUTPUT_FOLDER);
  const workbookSheet = spreadsheet.getSheetByName("Workbook");
  const bookTitle = workbookSheet
    ? workbookSheet.getRange("B5").getDisplayValue().trim()
    : "";
  const bookFolder = getOrCreateFolder_(
    buildsRoot,
    safeFolderName_(bookTitle || spreadsheet.getName()),
  );
  const timestamp = Utilities.formatDate(
    new Date(),
    spreadsheet.getSpreadsheetTimeZone(),
    "yyyy-MM-dd HH-mm-ss",
  );
  return bookFolder.createFolder(timestamp);
}

function getOrCreateFolder_(parent, name) {
  const matches = parent.getFoldersByName(name);
  return matches.hasNext() ? matches.next() : parent.createFolder(name);
}

function safeFolderName_(value) {
  const name = value.replace(/[\\/:*?"<>|]/g, "-").trim();
  return (name || "Workbook").slice(0, 90);
}

function rendererErrorMessage_(response) {
  const fallback = `Renderer failed with status ${response.getResponseCode()}.`;
  try {
    const parsed = JSON.parse(response.getContentText());
    return parsed.error || fallback;
  } catch (error) {
    return fallback;
  }
}

function showBuildResult_(ui, folder, files) {
  const links = files
    .map(
      (file) =>
        `<li><a href="${escapeHtml_(file.getUrl())}" target="_blank">` +
        `${escapeHtml_(file.getName())}</a></li>`,
    )
    .join("");
  const html = HtmlService.createHtmlOutput(
    `<p><strong>${files.length} PDFs created.</strong></p>` +
      `<p><a href="${escapeHtml_(folder.getUrl())}" target="_blank">` +
      "Open the Drive folder</a></p>" +
      `<ul>${links}</ul>`,
  )
    .setWidth(520)
    .setHeight(360);
  ui.showModalDialog(html, "4steps PDFs are ready");
}

function escapeHtml_(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
