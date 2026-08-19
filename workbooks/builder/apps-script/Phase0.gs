/**
 * The Phase 0 browser-compiler gate.
 *
 * BUILDER-ARCHITECTURE-DECISION.md accepts compiling workbooks in the author's
 * browser and saving approved PDFs through Apps Script to Drive. Everything in
 * that plan except the real Google environment has been proven locally, so this
 * file exists to test the part that cannot be proven anywhere else: opening the
 * preview window from the Sheet menu, and carrying the largest expected PDF back
 * through Apps Script into Drive.
 *
 * It is deliberately self-contained. When the gate is finished this file and its
 * dialog can be deleted without touching the renderer automation in Code.gs.
 *
 * No new OAuth scopes: the Sheet UI and Drive scopes Code.gs already requests
 * cover this, and the browser — not the script — fetches the compiler.
 */

const FOURSTEPS_PHASE0_BUILDS_FOLDER = "4steps PDF Builds";
const FOURSTEPS_PHASE0_FOLDER = "Phase 0 gate";
const FOURSTEPS_PHASE0_DEFAULT_PREVIEW_URL = "http://localhost:8787/preview.html";

/** Opens the launcher. Modeless, so the Sheet stays usable beside the preview. */
function openPhase0Gate() {
  const template = HtmlService.createTemplateFromFile("Phase0Dialog");
  template.previewUrl = phase0PreviewUrl_();
  SpreadsheetApp.getUi().showModelessDialog(
    template.evaluate().setWidth(460).setHeight(560),
    "4steps browser compiler gate",
  );
}

/**
 * Where the preview window lives.
 *
 * The gate runs against a bundle served locally; a later phase points the same
 * property at whichever static host Phase 1 chooses.
 */
function phase0PreviewUrl_() {
  const configured = (
    PropertiesService.getScriptProperties().getProperty("PREVIEW_URL") || ""
  ).trim();
  return configured || FOURSTEPS_PHASE0_DEFAULT_PREVIEW_URL;
}

/**
 * Save one browser-compiled PDF to Drive.
 *
 * This is the half of the round trip Apps Script owns: the preview window hands
 * the dialog the finished bytes, and they arrive here as base64 because that is
 * what `google.script.run` can carry.
 */
function savePhase0Pdf(payload) {
  if (!payload || !payload.base64) {
    throw new Error("The preview window sent no PDF.");
  }

  const bytes = Utilities.base64Decode(payload.base64);
  const name = phase0SafeName_(payload.name || "workbook.pdf");
  const folder = phase0RunFolder_(payload.session);
  const file = folder.createFile(Utilities.newBlob(bytes, "application/pdf", name));

  return {
    name: file.getName(),
    url: file.getUrl(),
    folderUrl: folder.getUrl(),
    bytes: bytes.length,
  };
}

/**
 * The folder for one gate run.
 *
 * Everything compiled during a single dialog session collects in one place, so
 * the Drive side of the record is one folder rather than a scatter of files.
 */
function phase0RunFolder_(session) {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  const parents = DriveApp.getFileById(spreadsheet.getId()).getParents();
  const parent = parents.hasNext() ? parents.next() : DriveApp.getRootFolder();
  const builds = phase0Folder_(parent, FOURSTEPS_PHASE0_BUILDS_FOLDER);
  const gate = phase0Folder_(builds, FOURSTEPS_PHASE0_FOLDER);
  return phase0Folder_(gate, phase0SafeName_(session || "run"));
}

function phase0Folder_(parent, name) {
  const matches = parent.getFoldersByName(name);
  return matches.hasNext() ? matches.next() : parent.createFolder(name);
}

function phase0SafeName_(value) {
  const name = String(value).replace(/[\\/:*?"<>|]/g, "-").trim();
  return (name || "workbook").slice(0, 90);
}
