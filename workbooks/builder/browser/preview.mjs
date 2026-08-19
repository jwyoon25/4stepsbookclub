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
  compileWorkbookPdf,
  loadWorkbookProject,
  PROJECT_SOURCE_FILES,
  readPdfCreator,
} from "/workbook-compiler.mjs";

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
  run: document.querySelector("#run"),
  compile: document.querySelector("#compile"),
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
  buildInfo: null,
  current: null,
  lastCompiled: null,
  driveOrigin: null,
  pendingSave: null,
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
  elements.fixture.replaceChildren(
    ...fixtures.map((fixture) => {
      const option = document.createElement("option");
      option.value = fixture.id;
      option.textContent = fixture.label;
      return option;
    }),
  );
}

// --- Compiling --------------------------------------------------------------

/** Which of the eight checks a workbook answers. */
function gateItemFor(fixture) {
  if (fixture.scope === "workbook") {
    return 5;
  }
  return fixture.edition === "student" ? 3 : 4;
}

async function compileFixture(fixture) {
  const bundle = await (
    await fetchOrThrow(`/fixtures/${fixture.id}.json`, `workbook ${fixture.id}`)
  ).json();

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

  show(fixture, pdf);
  log(
    `Compiled ${fixture.label} in ${milliseconds(duration)} with zero ` +
      `diagnostics (${megabytes(pdf.byteLength)}).`,
    "good",
  );
  return { pdf, duration };
}

async function compileSelected() {
  const fixture = state.fixtures.find(({ id }) => id === elements.fixture.value);
  if (!fixture || !state.compiler) {
    return;
  }

  setBusy(true);
  try {
    await compileFixture(fixture);
  } catch (error) {
    log(error.message, "bad");
  } finally {
    setBusy(false);
  }
}

function show(fixture, pdf) {
  clearPreview();

  const name = `${state.buildInfo.workbookId}-${fixture.id}-browser.pdf`;
  const url = URL.createObjectURL(new Blob([pdf], { type: "application/pdf" }));
  state.current = { fixture, pdf, url, name };

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
      record("Drive channel", `connected to ${event.origin}`);
      record("Drive run", message.session);
      verdict(1, `opened from the Sheet dialog at ${event.origin}`);
      log(`Connected to the Google Sheet dialog at ${event.origin}.`, "good");
    } else if (message.type === `${MESSAGE_PREFIX}-saved`) {
      state.pendingSave?.resolve(message);
    } else if (message.type === `${MESSAGE_PREFIX}-save-failed`) {
      state.pendingSave?.reject(new Error(message.error));
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

async function saveToDrive() {
  if (!state.current || !state.driveOrigin) {
    return null;
  }

  const { pdf, name, fixture } = state.current;
  elements.save.disabled = true;
  elements.save.textContent = "Saving…";
  log(`Sending ${name} (${megabytes(pdf.byteLength)}) to Apps Script…`);

  try {
    const saved = await new Promise((resolve, reject) => {
      state.pendingSave = { resolve, reject };
      window.opener.postMessage(
        {
          type: `${MESSAGE_PREFIX}-save`,
          name,
          fixture: fixture.id,
          bytes: pdf.byteLength,
          base64: toBase64(pdf),
        },
        state.driveOrigin,
      );
    });

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
    state.pendingSave = null;
    elements.save.disabled = false;
    elements.save.textContent = "Save to Google Drive";
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
async function verifyPdf(fixture, pdf) {
  const response = await fetch("/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fixture: fixture.id, pdfBase64: toBase64(pdf) }),
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
    await verifyPdf(state.current.fixture, state.current.pdf);
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
    for (const fixture of state.fixtures) {
      const item = gateItemFor(fixture);
      try {
        const { pdf, duration } = await compileFixture(fixture);
        verdict(
          item,
          `${fixture.edition}: ${megabytes(pdf.byteLength)} in ${milliseconds(duration)}`,
        );
        if (largest === null || pdf.byteLength > largest.pdf.byteLength) {
          largest = { fixture, pdf };
        }

        const result = await verifyPdf(fixture, pdf);
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
      `${clean} of ${state.fixtures.length} workbooks compiled cleanly, audited, ` +
        "and matched the native renderer.",
      clean === state.fixtures.length ? "good" : "bad",
    );

    // The largest PDF is the one the Drive transfer has to survive, and it is
    // the one left on screen at the end of the run.
    if (largest) {
      show(largest.fixture, largest.pdf);
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
elements.run.addEventListener("click", runEveryCheck);
elements.compile.addEventListener("click", compileSelected);
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
