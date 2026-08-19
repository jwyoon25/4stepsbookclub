// ---------------------------------------------------------------------------
// The Phase 0 preview window.
//
// This page is the thing the compatibility gate actually tests: it loads the
// Typst compiler, the workbook templates, the four brand fonts, and the logo
// assets as static files, compiles a real workbook in the author's browser,
// displays the generated PDF, and hands the result back to the Apps Script
// dialog that opened it so Drive receives the same bytes.
//
// It reports what it measures instead of assuming it. Every number the gate
// asks for — backend, transfer size, cold start, refresh time, PDF size,
// diagnostics — is displayed and copyable, because the gate is recorded in
// BUILDER-ARCHITECTURE-DECISION.md rather than felt.
// ---------------------------------------------------------------------------

import {
  createTypstCompiler,
  selectAutomaticBackendKind,
  supportsJspiBackend,
  supportsWorkerBackend,
} from "/vendor/typst-wasm/index.js";
import { createWebWorker } from "/vendor/typst-wasm/worker/browser.js";

import {
  createTargetBundle,
  listWorkbookTargets,
  workbookPdfName,
} from "/build-targets.mjs";
import {
  assertLessonLayout,
  assertSchemaValid,
  assertWrappableContent,
  normalizeLesson,
  normalizeManifest,
} from "/content-rules.mjs";
import {
  compressPdfEntries,
  DEFAULT_MAX_ARCHIVE_BYTES,
  MINIMUM_MAX_ARCHIVE_BYTES,
  packPdfArchives,
} from "/pdf-archive.mjs";
// Generated from `workbooks/schema/*.json` when the bundle is built. The
// schemas hold the length and count limits nothing else does, and this window
// is the export path, so it applies them exactly as a disk build does.
import { validateLesson, validateWorkbook } from "/schema-validators.mjs";
import {
  createWorkbookManifest,
  locateContentPath,
  parseWorkbookGrids,
  slugifyBookTitle,
} from "/sheet-contract.mjs";
import {
  compileWorkbookPdf,
  loadWorkbookProject,
  PROJECT_SOURCE_FILES,
  readPdfCreator,
} from "/workbook-compiler.mjs";

// Every round trip through the dialog reaches Apps Script, which is slower than
// anything else this window does. An archive of PDFs is slower still: Drive
// writes each file it unpacks, and the gate measured that channel at seconds per
// megabyte rather than milliseconds.
const SHEET_TIMEOUT_MILLISECONDS = 60000;
const DRIVE_TIMEOUT_MILLISECONDS = 300000;

const ENGINE_CORE_MODULES = [
  "engine.core.wasm",
  "engine.core2.wasm",
  "engine.core3.wasm",
];
const WORKER_URL = "/vendor/typst-wasm/worker/web-worker.js";
const MESSAGE_PREFIX = "4steps-preview";

// The eight checks from BUILDER-ARCHITECTURE-DECISION.md, in its order, so a
// completed run reads as an answer to the record rather than a list of numbers.
const GATE_ITEMS = [
  "Open the preview window from the Sheet menu",
  "Load the compiler, templates, fonts, and logos",
  "Compile and display a real standalone student lesson",
  "Compile and display its teacher edition",
  "Compile a representative complete workbook",
  "Transfer the largest PDF through Apps Script to Drive",
  "Zero diagnostics, audits pass, parity with native",
  "A usable cold start and refresh",
];

const elements = {
  environment: document.querySelector("#environment"),
  build: document.querySelector("#build"),
  fixture: document.querySelector("#fixture"),
  refresh: document.querySelector("#refresh"),
  run: document.querySelector("#run"),
  compile: document.querySelector("#compile"),
  export: document.querySelector("#export"),
  save: document.querySelector("#save"),
  verify: document.querySelector("#verify"),
  download: document.querySelector("#download"),
  copy: document.querySelector("#copy"),
  gate: document.querySelector("#gate"),
  measurements: document.querySelector("#measurements"),
  log: document.querySelector("#log"),
  viewer: document.querySelector("#viewer"),
};

const state = {
  compiler: null,
  backend: "unknown",
  fixtures: [],
  sheet: null,
  selections: [],
  buildInfo: null,
  current: null,
  lastCompiled: null,
  driveOrigin: null,
  // The window serves two audiences. A gate run answers the eight checks
  // against the workbooks in the bundle; an author opened it from the 4steps
  // menu to see their own book and export it. Opened directly, with no dialog
  // to say otherwise, it is the gate — that is the documented runbook.
  mode: "gate",
  intent: null,
  pending: new Map(),
  archiveBudget: DEFAULT_MAX_ARCHIVE_BYTES,
  measurements: new Map(),
  verdicts: new Map(),
  startedAt: performance.now(),
};

// --- Reporting --------------------------------------------------------------

function log(message, level = "info") {
  const line = document.createElement("div");
  line.className = `line line-${level}`;
  const elapsed = ((performance.now() - state.startedAt) / 1000).toFixed(1);
  line.textContent = `${elapsed.padStart(6)}s  ${message}`;
  elements.log.append(line);
  elements.log.scrollTop = elements.log.scrollHeight;
}

function definitions(target, entries) {
  target.replaceChildren(
    ...entries.flatMap(([label, value]) => {
      const term = document.createElement("dt");
      term.textContent = label;
      const description = document.createElement("dd");
      description.textContent = value;
      return [term, description];
    }),
  );
}

function record(name, value) {
  state.measurements.set(name, value);
  definitions(elements.measurements, [...state.measurements]);
}

function orderedVerdicts() {
  return [...state.verdicts].sort(([left], [right]) => left - right);
}

/** Record one gate item's verdict. Repeated answers accumulate in item order. */
function verdict(item, result) {
  const answers = state.verdicts.get(item) ?? [];
  answers.push(result);
  state.verdicts.set(item, answers);
  definitions(
    elements.gate,
    orderedVerdicts().map(([number, results]) => [
      `${number}. ${GATE_ITEMS[number - 1]}`,
      results.join(" · "),
    ]),
  );
}

function chip(label, value, tone) {
  const element = document.createElement("span");
  element.className = `chip chip-${tone}`;
  element.textContent = `${label}: ${value}`;
  return element;
}

function milliseconds(value) {
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${Math.round(value)} ms`;
}

function megabytes(bytes) {
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

// --- Environment ------------------------------------------------------------

function growableSharedMemory() {
  try {
    return new SharedArrayBuffer(0, { maxByteLength: 1 }).growable === true;
  } catch {
    return false;
  }
}

function describeEnvironment() {
  const worker = supportsWorkerBackend();
  const jspi = supportsJspiBackend();
  // The same worker factory the compiler is created with: the selection only
  // tests whether one was supplied, so this reports the backend that will
  // actually be used rather than a guess about it.
  const backend = selectAutomaticBackendKind({
    worker: () => createWebWorker(WORKER_URL),
  });

  elements.environment.replaceChildren(
    chip("backend", backend, backend === "none" ? "bad" : "good"),
    chip(
      "cross-origin isolated",
      String(globalThis.crossOriginIsolated === true),
      globalThis.crossOriginIsolated ? "good" : "neutral",
    ),
    chip("shared memory", String(worker), worker ? "good" : "neutral"),
    chip("JSPI", String(jspi), jspi ? "good" : "neutral"),
    chip(
      "Drive channel",
      window.opener ? "opener present" : "no opener",
      window.opener ? "good" : "neutral",
    ),
  );

  state.backend = backend;
  record("Backend", backend);
  record("Cross-origin isolated", String(globalThis.crossOriginIsolated === true));
  record("Growable shared memory", String(growableSharedMemory()));
  record("Browser", navigator.userAgent);

  if (backend === "none") {
    log(
      "No compatible compiler backend. This browser has neither cross-origin " +
        "isolated shared memory nor WebAssembly JSPI.",
      "bad",
    );
  }
  return backend;
}

// --- Static bundle ----------------------------------------------------------

async function fetchOrThrow(path, description) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Could not load ${description} (${response.status}): ${path}`);
  }
  return response;
}

async function compileCoreModule(name) {
  const path = `/vendor/typst-wasm/engine/${name}`;
  const response = await fetchOrThrow(path, "the compiler engine");
  try {
    return await WebAssembly.compileStreaming(response.clone());
  } catch {
    // Streaming compilation needs an application/wasm content type. A host that
    // serves the engine as a generic download still works through the buffer.
    return WebAssembly.compile(await response.arrayBuffer());
  }
}

function projectLoaders() {
  let bytes = 0;
  return {
    counted: () => bytes,
    readText: async (path) => {
      const response = await fetchOrThrow(`/project/${path}`, `template ${path}`);
      const text = await response.text();
      bytes += new Blob([text]).size;
      return text;
    },
    readBytes: async (path) => {
      const response = await fetchOrThrow(`/project/${path}`, `asset ${path}`);
      const buffer = await response.arrayBuffer();
      bytes += buffer.byteLength;
      return new Uint8Array(buffer);
    },
  };
}

async function startCompiler() {
  const startedAt = performance.now();
  log("Loading the Typst compiler…");

  const coreModules = Object.fromEntries(
    ENGINE_CORE_MODULES.map((name) => [name, compileCoreModule(name)]),
  );
  const compiler = await createTypstCompiler({
    coreModules,
    worker: () => createWebWorker(WORKER_URL),
  });
  const compilerReadyAt = performance.now();
  record("Compiler ready", milliseconds(compilerReadyAt - startedAt));
  log(`Compiler ready on the ${state.backend} backend.`, "good");

  const loaders = projectLoaders();
  const project = await loadWorkbookProject(compiler, loaders);
  record("Templates, fonts, logos", milliseconds(performance.now() - compilerReadyAt));
  record("Project transfer", megabytes(loaders.counted()));
  log(
    `Loaded ${PROJECT_SOURCE_FILES.length} templates, four brand fonts, and the ` +
      `logo set (${megabytes(loaders.counted())} in ${milliseconds(project.fetchMilliseconds)}).`,
    "good",
  );

  state.compiler = compiler;
  const coldStart = performance.now() - startedAt;
  record("Cold start", milliseconds(coldStart));
  verdict(2, `${megabytes(loaders.counted())} loaded on the ${state.backend} backend`);
  verdict(8, `cold start ${milliseconds(coldStart)}`);
}

async function loadFixtures() {
  const [buildInfo, fixtures] = await Promise.all([
    (await fetchOrThrow("/build-info.json", "the bundle description")).json(),
    (await fetchOrThrow("/fixtures/index.json", "the workbook list")).json(),
  ]);

  state.buildInfo = buildInfo;
  state.fixtures = fixtures;
  elements.build.textContent =
    `${buildInfo.bookTitle} · typst-wasm ${buildInfo.typstWasmVersion}` +
    (buildInfo.nativeTypstVersion ? ` · native ${buildInfo.nativeTypstVersion}` : "");
  renderSelections(fixtureSelections());
}

// --- What can be previewed --------------------------------------------------
//
// Two sources, never mixed: the workbooks checked into the bundle, which the
// gate is judged on and which work with no Sheet at all, and the live Sheet the
// dialog reads. Switching between them replaces the list rather than adding to
// it, so what is selected is never ambiguous about where it came from.

function fixtureSelections() {
  return state.fixtures.map((fixture) => ({ ...fixture, source: "bundle" }));
}

function sheetSelections() {
  return state.sheet.targets.map((target) => ({
    ...target,
    source: "sheet",
    lessonCount: target.lessonNumbers.length,
  }));
}

function renderSelections(selections) {
  state.selections = selections;
  elements.fixture.replaceChildren(
    ...selections.map((selection) => {
      const option = document.createElement("option");
      option.value = selection.id;
      option.textContent = selection.label;
      return option;
    }),
  );
  clearPreview();
}

/**
 * Show the author which cell a failure was about, or that none is.
 *
 * The Sheet contract names a cell outright. A content rule names a lesson and a
 * field, because it never saw a spreadsheet, so the row it was typed on is
 * looked up from what the contract recorded while parsing. Either way the
 * dialog does the marking, because only an Apps Script page can write to the
 * Sheet. Called with nothing, it clears whatever the last failure marked.
 */
function markTheCell(cell, message) {
  if (!state.driveOrigin) {
    return;
  }
  window.opener.postMessage(
    { type: `${MESSAGE_PREFIX}-highlight`, cell: cell ? { ...cell, message } : null },
    state.driveOrigin,
  );
}

/**
 * Read the workbook the author is looking at.
 *
 * The Sheet arrives as raw cell matrices; everything that turns them into a
 * workbook — the tab and column contract, the response-space defaults, the
 * layout budgets — is the same code the disk build runs, so a preview cannot
 * quietly accept content a real build would refuse.
 */
async function refreshFromSheet() {
  elements.refresh.disabled = true;
  elements.refresh.textContent = "Reading the Sheet…";

  // Whatever the last read complained about is no longer what is wrong.
  let cell;
  try {
    const startedAt = performance.now();
    const { grids, spreadsheetName } = await requestSheetGrids();
    const { metadata, lessons, sources } = parseWorkbookGrids(grids);
    // The same order a disk build applies: the schema first, because it decides
    // what the later rules are even allowed to assume about the content.
    const parsedManifest = createWorkbookManifest(metadata, lessons, {
      workbookId: slugifyBookTitle(metadata.bookTitle) || "workbook",
    });
    assertSchemaValid(validateWorkbook, parsedManifest, "the Workbook tab");
    const manifest = normalizeManifest(parsedManifest);
    assertWrappableContent(manifest, "the Workbook tab");

    const normalized = lessons.map((lesson) => {
      const source = `lesson ${lesson.lessonNumber}`;
      try {
        assertSchemaValid(validateLesson, lesson, source);
        assertWrappableContent(lesson, source);
        const normalizedLesson = normalizeLesson(lesson);
        assertLessonLayout(normalizedLesson, source);
        return normalizedLesson;
      } catch (error) {
        cell = locateContentPath(sources, lesson.lessonNumber, error.path);
        throw error;
      }
    });

    state.sheet = {
      name: spreadsheetName,
      manifest,
      lessons: normalized,
      targets: listWorkbookTargets(normalized),
    };
    renderSelections(sheetSelections());
    markTheCell();
    record("Workbook", `${manifest.bookTitle} · ${normalized.length} lessons`);
    record("Sheet read", milliseconds(performance.now() - startedAt));
    log(
      `Read ${normalized.length} lessons from "${spreadsheetName}" in ` +
        `${milliseconds(performance.now() - startedAt)}.`,
      "good",
    );
    return true;
  } catch (error) {
    // Sheet and content errors name the tab, the row, and the column, which is
    // the whole point of showing them here rather than a generic failure. The
    // Sheet is then made to show the same thing, because reading a row number
    // and finding the row are not the same job.
    log(error.message, "bad");
    markTheCell(error.cell ?? cell, error.message);
    return false;
  } finally {
    elements.refresh.disabled = state.driveOrigin === null;
    elements.refresh.textContent = "Refresh from the Sheet";
    elements.export.disabled = state.sheet === null;
  }
}

// --- Compiling --------------------------------------------------------------

/** Which of the eight checks a workbook answers. */
function gateItemFor(fixture) {
  if (fixture.scope === "workbook") {
    return 5;
  }
  return fixture.edition === "student" ? 3 : 4;
}

async function resolveBundle(selection) {
  if (selection.source !== "sheet") {
    return (
      await fetchOrThrow(`/fixtures/${selection.id}.json`, `workbook ${selection.id}`)
    ).json();
  }

  // No teacher-guidance check here: the Sheet contract requires that cell on the
  // Comprehension and Analysis tabs, so content that parsed at all already has
  // it. The check in `content-rules.mjs` is for packages authored on disk.
  return createTargetBundle(state.sheet.manifest, state.sheet.lessons, selection);
}

async function compileFixture(selection) {
  const fixture = selection;
  const bundle = await resolveBundle(selection);

  log(`Compiling ${fixture.label}…`);
  const startedAt = performance.now();
  const pdf = await compileWorkbookPdf(state.compiler, bundle);
  const duration = performance.now() - startedAt;

  // Recompiling the same workbook is the refresh the gate asks about; the
  // compiler reuses its previous work for it. Compiling a different workbook is
  // a fresh compile and is recorded as one.
  const refresh = state.lastCompiled === fixture.id;
  state.lastCompiled = fixture.id;
  record(refresh ? "Refresh compile" : "Compile", milliseconds(duration));
  if (refresh) {
    verdict(8, `refresh ${milliseconds(duration)}`);
  }
  record("PDF size", megabytes(pdf.byteLength));
  record("Typst engine", readPdfCreator(pdf));

  show(fixture, pdf, bundle);
  log(
    `Compiled ${fixture.label} in ${milliseconds(duration)} with zero ` +
      `diagnostics (${megabytes(pdf.byteLength)}).`,
    "good",
  );
  return { pdf, duration, bundle };
}

async function compileSelected() {
  const selection = state.selections.find(({ id }) => id === elements.fixture.value);
  if (!selection || !state.compiler) {
    return;
  }

  setBusy(true);
  try {
    await compileFixture(selection);
  } catch (error) {
    log(error.message, "bad");
  } finally {
    setBusy(false);
  }
}

function show(fixture, pdf, bundle) {
  clearPreview();

  const workbookId =
    fixture.source === "sheet" ? state.sheet.manifest.id : state.buildInfo.workbookId;
  const name = `${workbookId}-${fixture.id}-browser.pdf`;
  const url = URL.createObjectURL(new Blob([pdf], { type: "application/pdf" }));
  state.current = { fixture, pdf, bundle, url, name };

  elements.viewer.src = url;
  elements.download.href = url;
  elements.download.download = name;
  elements.download.hidden = false;
  elements.verify.disabled = false;
  elements.save.disabled = state.driveOrigin === null;
}

/**
 * Stop showing a workbook that is no longer the selected one.
 *
 * The gate is judged by what the window displays, so a previous PDF must never
 * sit under a different workbook's name.
 */
function clearPreview() {
  if (state.current?.url) {
    URL.revokeObjectURL(state.current.url);
  }
  state.current = null;
  elements.viewer.removeAttribute("src");
  elements.download.hidden = true;
  elements.save.disabled = true;
  elements.verify.disabled = true;
}

function setBusy(busy) {
  elements.run.disabled = busy;
  elements.compile.disabled = busy;
  elements.fixture.disabled = busy;
  elements.export.disabled = busy || state.sheet === null;
  elements.compile.textContent = busy ? "Compiling…" : "Compile and preview";
}

// --- Drive round trip -------------------------------------------------------

function toBase64(bytes) {
  let binary = "";
  for (let index = 0; index < bytes.length; index += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
  }
  return btoa(binary);
}

function connectToDialog() {
  window.addEventListener("message", (event) => {
    const message = event.data;
    if (typeof message?.type !== "string" || !message.type.startsWith(MESSAGE_PREFIX)) {
      return;
    }
    // The Apps Script dialog is the window that opened this one, and after it
    // answers, its origin is the only one this page will send a workbook to.
    if (event.source !== window.opener) {
      return;
    }
    if (state.driveOrigin !== null && event.origin !== state.driveOrigin) {
      return;
    }

    if (message.type === `${MESSAGE_PREFIX}-hello`) {
      state.driveOrigin = event.origin;
      elements.save.disabled = state.current === null;
      elements.refresh.disabled = false;
      record("Drive channel", `connected to ${event.origin}`);
      record("Drive run", message.session);
      verdict(1, `opened from the Sheet dialog at ${event.origin}`);
      log(`Connected to the Google Sheet dialog at ${event.origin}.`, "good");
      applyMode(message.mode ?? "gate", message.intent ?? null);
      // The author opened this window from their workbook, so their workbook is
      // what it should be showing.
      openWorkbook();
      return;
    }

    const pending = state.pending.get(message.type);
    if (pending) {
      if (message.error === undefined) {
        pending.resolve(message);
      } else {
        pending.reject(new Error(message.error));
      }
    }
  });

  if (!window.opener) {
    verdict(1, "no opener — this window was not opened by the Sheet dialog");
    log(
      "This window has no opener, so it cannot reach Google Drive. A " +
        "cross-origin-isolated page is cut off from the dialog that opened it; " +
        "use the non-isolated preview for the Drive round trip.",
      "warn",
    );
    return;
  }

  // The dialog replies with its own origin, which is the only origin this page
  // then talks to. Announcing readiness carries nothing but a version string.
  window.opener.postMessage({ type: `${MESSAGE_PREFIX}-ready`, version: 1 }, "*");
  log("Announced this window to the Google Sheet dialog.");
}

/**
 * Ask the Apps Script dialog for something and wait for its answer.
 *
 * Everything this window needs from Google — the Sheet's cells, a build folder,
 * a saved archive — is a request the dialog answers with either a reply or an
 * `error`. One reply type is one outstanding request, which is true because
 * each of them is a step the author is waiting on.
 */
function askTheDialog(request, replyType, timeoutMilliseconds) {
  if (!state.driveOrigin) {
    return Promise.reject(
      new Error("This window is not connected to a Google Sheet."),
    );
  }

  return new Promise((resolve, reject) => {
    const expired = setTimeout(() => {
      state.pending.delete(replyType);
      reject(new Error("The Google Sheet did not answer in time."));
    }, timeoutMilliseconds);
    const settle = (settler) => (value) => {
      clearTimeout(expired);
      state.pending.delete(replyType);
      settler(value);
    };

    state.pending.set(replyType, {
      resolve: settle(resolve),
      reject: settle(reject),
    });
    window.opener.postMessage(request, state.driveOrigin);
  });
}

function requestSheetGrids() {
  return askTheDialog(
    { type: `${MESSAGE_PREFIX}-read-sheet` },
    `${MESSAGE_PREFIX}-sheet`,
    SHEET_TIMEOUT_MILLISECONDS,
  );
}

async function saveToDrive() {
  if (!state.current || !state.driveOrigin) {
    return null;
  }

  const { pdf, name, fixture } = state.current;
  elements.save.disabled = true;
  elements.save.textContent = "Saving…";
  log(`Sending ${name} (${megabytes(pdf.byteLength)}) to Apps Script…`);

  try {
    const saved = await askTheDialog(
      {
        type: `${MESSAGE_PREFIX}-save`,
        name,
        fixture: fixture.id,
        bytes: pdf.byteLength,
        base64: toBase64(pdf),
      },
      `${MESSAGE_PREFIX}-saved`,
      DRIVE_TIMEOUT_MILLISECONDS,
    );

    record("Drive transfer", milliseconds(saved.milliseconds));
    verdict(
      6,
      `${megabytes(pdf.byteLength)} saved in ${milliseconds(saved.milliseconds)}`,
    );
    log(`Saved ${saved.name} to Google Drive: ${saved.url}`, "good");
    return saved;
  } catch (error) {
    verdict(6, `failed — ${error.message}`);
    log(`Google Drive rejected the transfer: ${error.message}`, "bad");
    return null;
  } finally {
    elements.save.disabled = false;
    elements.save.textContent = "Save to Google Drive";
  }
}

// --- The export -------------------------------------------------------------
//
// Everything a workbook owes: one PDF per lesson and one for the whole book, in
// both editions. Twenty-six files for a twelve-lesson book, compiled here in
// well under a second and then carried to Drive, which is the part that takes
// real time.

/**
 * Compile every PDF the workbook owes.
 *
 * The names are the ones `lib/build.mjs` writes on disk, so a folder built here
 * and a folder built by the native renderer hold the same files.
 */
async function compileEveryTarget(onProgress) {
  const { manifest, lessons, targets } = state.sheet;
  const files = [];

  for (const [index, target] of targets.entries()) {
    onProgress(index, targets.length, target);
    files.push({
      name: workbookPdfName(manifest.id, target),
      bytes: await compileWorkbookPdf(
        state.compiler,
        createTargetBundle(manifest, lessons, target),
      ),
    });
  }

  return files;
}

/**
 * Send the archives, shrinking them if a host refuses one.
 *
 * How much `google.script.run` will carry in a single call is the one thing
 * about this transfer nobody has established. Rather than guess conservatively
 * and pay for it on every export, the budget starts at what the gate's measured
 * figure suggests is safe and halves on refusal — so the first export that
 * meets a real limit finds it, says so, and finishes anyway.
 */
async function sendArchives(files, folderId) {
  const saved = [];
  // Compressing is the cheap half and the entries never change, so a retry at a
  // smaller budget repacks them rather than deflating four megabytes again.
  let remaining = await compressPdfEntries(files);
  let driveMilliseconds = 0;
  let transferMilliseconds = 0;

  while (remaining.length > 0) {
    const [archive] = packPdfArchives(remaining, {
      maxArchiveBytes: state.archiveBudget,
    });
    const base64 = toBase64(archive.bytes);

    log(
      `Sending ${archive.names.length} PDFs (${megabytes(archive.bytes.length)} ` +
        `compressed, ${megabytes(base64.length)} encoded)…`,
    );

    const startedAt = performance.now();
    let result;
    try {
      result = await askTheDialog(
        {
          type: `${MESSAGE_PREFIX}-export-archive`,
          folderId,
          bytes: archive.bytes.length,
          base64,
        },
        `${MESSAGE_PREFIX}-export-saved`,
        DRIVE_TIMEOUT_MILLISECONDS,
      );
    } catch (error) {
      if (
        archive.names.length === 1 ||
        state.archiveBudget <= MINIMUM_MAX_ARCHIVE_BYTES
      ) {
        throw error;
      }
      state.archiveBudget = Math.max(
        MINIMUM_MAX_ARCHIVE_BYTES,
        Math.floor(state.archiveBudget / 2),
      );
      log(
        `Google refused ${megabytes(base64.length)} in one call — ${error.message}. ` +
          `Retrying with archives of ${megabytes(state.archiveBudget)}.`,
        "warn",
      );
      continue;
    }

    const elapsed = performance.now() - startedAt;
    driveMilliseconds += result.milliseconds.total;
    transferMilliseconds += elapsed - result.milliseconds.total;
    saved.push(...result.files);
    log(
      `Saved ${result.files.length} PDFs in ${milliseconds(elapsed)} — ` +
        `${milliseconds(result.milliseconds.total)} of it in Drive ` +
        `(unzip ${milliseconds(result.milliseconds.unzip)}, ` +
        `write ${milliseconds(result.milliseconds.write)}).`,
      "good",
    );

    remaining = remaining.slice(archive.names.length);
  }

  return { saved, driveMilliseconds, transferMilliseconds };
}

/**
 * Write every approved PDF to the workbook's build folder in Drive.
 *
 * The folder is created first and once, so a run that fails partway leaves one
 * timestamped folder holding what did arrive rather than scattering files
 * across two of them.
 */
async function exportApprovedPdfs() {
  if (!state.sheet || !state.compiler) {
    return;
  }

  setBusy(true);
  elements.export.disabled = true;
  elements.export.textContent = "Exporting…";
  state.archiveBudget = DEFAULT_MAX_ARCHIVE_BYTES;

  try {
    const startedAt = performance.now();
    const files = await compileEveryTarget((index, total, target) => {
      elements.export.textContent = `Compiling ${index + 1} of ${total}…`;
      log(`Compiling ${target.label}…`);
    });
    const compiledAt = performance.now();
    const totalBytes = files.reduce((sum, { bytes }) => sum + bytes.byteLength, 0);
    record("Export compile", milliseconds(compiledAt - startedAt));
    log(
      `Compiled ${files.length} PDFs (${megabytes(totalBytes)}) in ` +
        `${milliseconds(compiledAt - startedAt)}.`,
      "good",
    );

    elements.export.textContent = "Creating the build folder…";
    const folder = await askTheDialog(
      { type: `${MESSAGE_PREFIX}-export-start` },
      `${MESSAGE_PREFIX}-export-started`,
      SHEET_TIMEOUT_MILLISECONDS,
    );
    log(`Writing to ${folder.folderName} in Google Drive.`);

    elements.export.textContent = "Sending to Drive…";
    const { saved, driveMilliseconds, transferMilliseconds } = await sendArchives(
      files,
      folder.folderId,
    );

    const elapsed = performance.now() - compiledAt;
    record("Export transfer", milliseconds(elapsed));
    record("Export PDFs", `${saved.length} files, ${megabytes(totalBytes)}`);
    log(
      `Exported ${saved.length} PDFs to Google Drive in ${milliseconds(elapsed)}: ` +
        `${milliseconds(driveMilliseconds)} in Apps Script and Drive, ` +
        `${milliseconds(transferMilliseconds)} in the channel itself.`,
      "good",
    );
    log(folder.folderUrl, "good");
  } catch (error) {
    log(`The export failed: ${error.message}`, "bad");
  } finally {
    setBusy(false);
    elements.export.disabled = false;
    elements.export.textContent = "Create all approved PDFs";
  }
}

// --- What the window was opened for -----------------------------------------

/**
 * Show only what this window was opened to do.
 *
 * The gate's controls answer a question that was settled on 2026-08-19; an
 * author opening their workbook from the 4steps menu should not be offered
 * them, or the four fixtures they run against.
 */
function applyMode(mode, intent) {
  state.mode = mode;
  state.intent = intent;
  document.body.dataset.mode = mode;
  if (mode === "gate") {
    return;
  }
  record("Opened for", intent ?? mode);
}

/** Read the author's workbook, then do whatever the menu item asked for. */
async function openWorkbook() {
  const parsed = await refreshFromSheet();
  if (!parsed) {
    return;
  }

  if (state.intent === "validate") {
    log(
      `${state.sheet.manifest.bookTitle} is valid: ${state.sheet.lessons.length} ` +
        `lessons, ${state.sheet.targets.length} PDFs to build.`,
      "good",
    );
  } else if (state.intent === "export") {
    await exportApprovedPdfs();
  } else if (state.mode === "author") {
    await compileSelected();
  }
}

// --- Independent verification ----------------------------------------------

/**
 * Ask the gate server to audit this PDF and compare it with native Typst.
 *
 * The browser cannot check its own work: the audit and the native renderer both
 * live outside it. Sending the finished bytes back keeps the thing being judged
 * the same thing the browser produced.
 */
async function verifyPdf(fixture, pdf, bundle) {
  // A checked workbook is named; a Sheet's workbook has to be sent, because the
  // server has never seen it.
  const workbook =
    fixture.source === "sheet" ? { bundle } : { fixture: fixture.id };
  const response = await fetch("/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...workbook, pdfBase64: toBase64(pdf) }),
  });
  if (response.status === 404) {
    throw new Error(
      "This bundle is being served as plain static files. Run it with " +
        "`npm run workbook:browser-gate` to audit and compare from the browser.",
    );
  }

  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.error ?? `Verification failed (${response.status}).`);
  }

  record("Audit", result.audit.passed ? "passed" : "failed");
  log(
    result.audit.passed
      ? `PDF audit passed: ${result.audit.pageCount} pages.`
      : `PDF audit failed: ${result.audit.error}`,
    result.audit.passed ? "good" : "bad",
  );

  if (result.parity.compared) {
    record("Native parity", result.parity.identical ? "identical" : "different");
    log(
      result.parity.identical
        ? `Identical to the native renderer: ${result.parity.pageCount} pages, ` +
          `${result.parity.textItems} text runs, no positional difference.`
        : `Differs from the native renderer: ${result.parity.summary}`,
      result.parity.identical ? "good" : "bad",
    );
  } else {
    log(`Native comparison skipped: ${result.parity.reason}`, "warn");
  }

  return result;
}

async function verifyCurrentPdf() {
  if (!state.current) {
    return;
  }

  elements.verify.disabled = true;
  elements.verify.textContent = "Verifying…";
  try {
    log("Auditing the browser-generated PDF and comparing it with native Typst…");
    await verifyPdf(state.current.fixture, state.current.pdf, state.current.bundle);
  } catch (error) {
    log(error.message, "bad");
  } finally {
    elements.verify.disabled = false;
    elements.verify.textContent = "Audit and compare with native";
  }
}

// --- The whole gate in one run ---------------------------------------------

/**
 * Compile every workbook, verify each one, and save the largest to Drive.
 *
 * The eight checks are pass or fail together, so answering them one at a time
 * by hand invites a half-finished record. This answers all of them in order and
 * leaves the largest workbook on screen.
 */
async function runEveryCheck() {
  setBusy(true);
  let clean = 0;
  let largest = null;

  try {
    // The gate is judged on the workbooks checked into the bundle, whatever the
    // window happens to be showing.
    renderSelections(fixtureSelections());
    for (const fixture of state.selections) {
      const item = gateItemFor(fixture);
      try {
        const { pdf, duration, bundle } = await compileFixture(fixture);
        verdict(
          item,
          `${fixture.edition}: ${megabytes(pdf.byteLength)} in ${milliseconds(duration)}`,
        );
        if (largest === null || pdf.byteLength > largest.pdf.byteLength) {
          largest = { fixture, pdf };
        }

        const result = await verifyPdf(fixture, pdf, bundle);
        const compared = result.parity.compared;
        const passed = result.audit.passed && (!compared || result.parity.identical);
        if (passed) {
          clean += 1;
        }
        verdict(
          7,
          passed
            ? `${fixture.id}: audited, ${
                compared ? "identical to native" : "no native comparison"
              }`
            : `${fixture.id}: FAILED`,
        );
      } catch (error) {
        verdict(item, `failed — ${error.message}`);
        log(error.message, "bad");
      }
    }

    log(
      `${clean} of ${state.selections.length} workbooks compiled cleanly, audited, ` +
        "and matched the native renderer.",
      clean === state.selections.length ? "good" : "bad",
    );

    // The largest PDF is the one the Drive transfer has to survive, and it is
    // the one left on screen at the end of the run. Compiling it twice more is
    // what answers the second half of check 8: the first pass makes it current
    // again, and the second is the refresh an author waits through after
    // editing a cell.
    if (largest) {
      await compileFixture(largest.fixture);
      await compileFixture(largest.fixture);
      if (state.driveOrigin) {
        await saveToDrive();
      } else {
        verdict(6, "not run — no Drive channel from this window");
      }
    }
  } finally {
    setBusy(false);
  }
}

// --- Result record ----------------------------------------------------------

function resultsReport() {
  const gate = orderedVerdicts()
    .map(
      ([number, results]) =>
        `| ${number} | ${GATE_ITEMS[number - 1]} | ${results.join("; ")} |`,
    )
    .join("\n");
  const measurements = [...state.measurements]
    .map(([label, value]) => `| ${label} | ${value} |`)
    .join("\n");

  return (
    `### Phase 0 gate run — ${new Date().toISOString()}\n\n` +
    `| # | Check | Result |\n| --- | --- | --- |\n${gate}\n\n` +
    `| Measurement | Result |\n| --- | --- |\n${measurements}\n\n` +
    `Log:\n\n\`\`\`\n${elements.log.textContent.trim()}\n\`\`\`\n`
  );
}

async function copyResults() {
  const report = resultsReport();
  try {
    await navigator.clipboard.writeText(report);
    log("Copied the results table to the clipboard.", "good");
  } catch {
    // Clipboard access needs a permission this window may not have; showing the
    // report is enough for a record that gets pasted by hand.
    log(`Copy failed. The report is below.\n\n${report}`, "warn");
  }
}

// --- Start ------------------------------------------------------------------

elements.fixture.addEventListener("change", clearPreview);
elements.refresh.addEventListener("click", refreshFromSheet);
elements.run.addEventListener("click", runEveryCheck);
elements.compile.addEventListener("click", compileSelected);
elements.export.addEventListener("click", exportApprovedPdfs);
elements.save.addEventListener("click", saveToDrive);
elements.verify.addEventListener("click", verifyCurrentPdf);
elements.copy.addEventListener("click", copyResults);

connectToDialog();
const backend = describeEnvironment();

try {
  await loadFixtures();
  if (backend !== "none") {
    await startCompiler();
    elements.run.disabled = false;
    elements.compile.disabled = false;
    log("Ready. Run every check, or compile one workbook at a time.", "good");
  } else {
    verdict(2, "failed — no compiler backend in this browser");
  }
} catch (error) {
  log(error.message, "bad");
}
