#!/usr/bin/env node

// ---------------------------------------------------------------------------
// The Phase 0 gate server.
//
// It serves the generated browser bundle with the headers a real static host
// would send, and it answers one request the browser cannot answer for itself:
// whether the PDF it just produced passes the existing workbook audit and
// matches what the native Typst CLI makes of the same content. That turns the
// browser's own output into the evidence, instead of a lookalike compiled here.
//
// It binds to the loopback interface. Nothing about it is meant to be exposed.
// ---------------------------------------------------------------------------

import { createServer } from "node:http";
import { mkdir, mkdtemp, readFile, rm, stat, writeFile } from "node:fs/promises";
import { createReadStream } from "node:fs";
import { dirname, extname, join, relative, resolve, sep } from "node:path";
import { pipeline } from "node:stream/promises";
import { fileURLToPath } from "node:url";

import {
  browserBundleDefaults,
  BUNDLE_CACHE_RULES,
} from "../lib/browser-bundle.mjs";
import { compileBundleWithNativeTypst, WorkbookBuildError } from "../lib/build.mjs";
import { auditWorkbookPdf, WorkbookPdfAuditError } from "../lib/pdf-audit.mjs";
import { comparePdfDocuments } from "../lib/render-parity.mjs";

const defaults = browserBundleDefaults();
const workbooksRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
// Native comparisons compile inside the workbook root, because that is the root
// the Typst CLI is given and it cannot read anything outside it.
const temporaryParent = resolve(workbooksRoot, "output/.build");
const DEFAULT_PORT = 8787;
const MAXIMUM_UPLOAD_BYTES = 32 * 1024 * 1024;

const CONTENT_TYPES = new Map([
  [".html", "text/html; charset=utf-8"],
  [".css", "text/css; charset=utf-8"],
  [".mjs", "text/javascript; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".wasm", "application/wasm"],
  [".typ", "text/plain; charset=utf-8"],
  [".ttf", "font/ttf"],
  [".png", "image/png"],
  [".pdf", "application/pdf"],
]);

const argumentsAfterCommand = process.argv.slice(2);

if (argumentsAfterCommand.includes("--help") || argumentsAfterCommand.includes("-h")) {
  console.log(
    "Usage: npm run workbook:browser-gate -- [--port number] [--bundle path]",
  );
  console.log(`Default port:   ${DEFAULT_PORT}`);
  console.log(`Default bundle: ${relative(process.cwd(), defaults.outputDirectory)}`);
  process.exit(0);
}

let port = DEFAULT_PORT;
let bundleDirectory = defaults.outputDirectory;

for (let index = 0; index < argumentsAfterCommand.length; index += 1) {
  const argument = argumentsAfterCommand[index];
  if (argument === "--port") {
    const value = Number(argumentsAfterCommand[index + 1]);
    if (!Number.isInteger(value) || value < 1 || value > 65535) {
      console.error("--port requires a port number.");
      process.exit(2);
    }
    port = value;
    index += 1;
  } else if (argument === "--bundle") {
    const value = argumentsAfterCommand[index + 1];
    if (!value) {
      console.error("--bundle requires a path.");
      process.exit(2);
    }
    bundleDirectory = resolve(value);
    index += 1;
  } else {
    console.error(`Unexpected argument: ${argument}`);
    process.exit(2);
  }
}

try {
  await stat(join(bundleDirectory, "build-info.json"));
} catch {
  console.error(
    `No browser bundle at ${relative(process.cwd(), bundleDirectory)}.\n` +
      "Run: npm run workbook:browser-bundle",
  );
  process.exit(1);
}

function matchesPattern(pathname, pattern) {
  return pattern.endsWith("/*")
    ? pathname.startsWith(pattern.slice(0, -1))
    : pathname === pattern;
}

function cacheControlFor(pathname) {
  const rule = BUNDLE_CACHE_RULES.find(([pattern]) =>
    matchesPattern(pathname, pattern),
  );
  return rule ? rule[1] : "no-cache";
}

function resolveBundleFile(pathname) {
  const filePath = resolve(bundleDirectory, `.${pathname}`);
  const inside = relative(bundleDirectory, filePath);
  if (inside.startsWith(`..${sep}`) || inside === "..") {
    return null;
  }
  return filePath;
}

function sendJson(response, status, body) {
  const payload = JSON.stringify(body);
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(payload),
    "Cache-Control": "no-store",
  });
  response.end(payload);
}

async function serveFile(request, response, pathname) {
  const filePath = resolveBundleFile(pathname);
  if (!filePath) {
    sendJson(response, 403, { error: "Path is outside the bundle." });
    return;
  }

  let information;
  try {
    information = await stat(filePath);
  } catch {
    sendJson(response, 404, { error: `Not in the bundle: ${pathname}` });
    return;
  }
  if (!information.isFile()) {
    sendJson(response, 404, { error: `Not a file: ${pathname}` });
    return;
  }

  const headers = {
    "Content-Type": CONTENT_TYPES.get(extname(filePath)) ?? "application/octet-stream",
    "Content-Length": information.size,
    "Cache-Control": cacheControlFor(pathname),
  };

  // The isolated copy of the preview page is the whole reason it exists: these
  // two headers are what let a browser without JSPI reach the worker backend.
  if (pathname.startsWith("/isolated/")) {
    headers["Cross-Origin-Opener-Policy"] = "same-origin";
    headers["Cross-Origin-Embedder-Policy"] = "require-corp";
  }

  response.writeHead(200, headers);
  if (request.method === "HEAD") {
    response.end();
    return;
  }
  await pipeline(createReadStream(filePath), response);
}

async function readRequestBody(request) {
  const chunks = [];
  let bytes = 0;
  for await (const chunk of request) {
    bytes += chunk.length;
    if (bytes > MAXIMUM_UPLOAD_BYTES) {
      throw new Error("The uploaded PDF is larger than this server accepts.");
    }
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

async function auditBrowserPdf(pdfPath, fixture) {
  try {
    const report = await auditWorkbookPdf(pdfPath, {
      scope: fixture.scope,
      edition: fixture.edition,
      // The audit only counts the lessons, so their content is irrelevant here:
      // the PDF under test is the thing being described, not the source.
      lessons: Array.from({ length: fixture.lessonCount }, () => ({})),
    });
    return { passed: true, pageCount: report.pageCount };
  } catch (error) {
    if (error instanceof WorkbookPdfAuditError) {
      return { passed: false, error: error.message };
    }
    throw error;
  }
}

async function compareWithNativeTypst(pdfPath, fixture, temporaryDirectory) {
  const bundlePath = join(temporaryDirectory, `${fixture.id}.json`);
  const nativePath = join(temporaryDirectory, `${fixture.id}-native.pdf`);
  await writeFile(bundlePath, `${JSON.stringify(fixture.bundle, null, 2)}\n`);

  try {
    await compileBundleWithNativeTypst(bundlePath, nativePath);
  } catch (error) {
    if (error instanceof WorkbookBuildError) {
      return { compared: false, reason: error.message };
    }
    throw error;
  }

  const parity = await comparePdfDocuments(nativePath, pdfPath);
  return { compared: true, ...parity };
}

/**
 * Identify the workbook a request is asking about.
 *
 * A checked workbook is named and read from the bundle. A workbook compiled
 * from a live Sheet has never been here before, so the browser sends the bundle
 * it compiled, and that is what gets compiled natively for the comparison.
 */
async function resolveVerificationSubject(payload) {
  if (payload.bundle) {
    const { build, lessons } = payload.bundle;
    if (!build?.scope || !build?.edition || !Array.isArray(lessons)) {
      throw new WorkbookBuildError("The request carried an unrecognizable workbook.");
    }
    return {
      id: `${build.scope}-${build.edition}-sheet`,
      scope: build.scope,
      edition: build.edition,
      lessonCount: lessons.length,
      bundle: payload.bundle,
    };
  }

  const fixtures = JSON.parse(
    await readFile(join(bundleDirectory, "fixtures/index.json"), "utf8"),
  );
  const fixture = fixtures.find(({ id }) => id === payload.fixture);
  if (!fixture) {
    throw new WorkbookBuildError(`Unknown workbook: ${payload.fixture}`);
  }

  return {
    ...fixture,
    bundle: JSON.parse(
      await readFile(join(bundleDirectory, `fixtures/${fixture.id}.json`), "utf8"),
    ),
  };
}

async function verify(request, response) {
  let payload;
  try {
    payload = JSON.parse((await readRequestBody(request)).toString("utf8"));
  } catch (error) {
    sendJson(response, 400, { error: error.message });
    return;
  }

  let fixture;
  try {
    fixture = await resolveVerificationSubject(payload);
  } catch (error) {
    sendJson(response, 400, { error: error.message });
    return;
  }
  if (typeof payload.pdfBase64 !== "string" || payload.pdfBase64.length === 0) {
    sendJson(response, 400, { error: "The request carried no PDF." });
    return;
  }

  await mkdir(temporaryParent, { recursive: true });
  const temporaryDirectory = await mkdtemp(join(temporaryParent, "verify-"));
  const pdfPath = join(temporaryDirectory, `${fixture.id}-browser.pdf`);

  try {
    await writeFile(pdfPath, Buffer.from(payload.pdfBase64, "base64"));
    const audit = await auditBrowserPdf(pdfPath, fixture);
    const parity = await compareWithNativeTypst(pdfPath, fixture, temporaryDirectory);
    console.log(
      `verified ${fixture.id}: audit ${audit.passed ? "passed" : "FAILED"}; ` +
        `native comparison ${parity.compared ? parity.summary : "skipped"}`,
    );
    sendJson(response, 200, { fixture: fixture.id, audit, parity });
  } catch (error) {
    console.error(`verification of ${fixture.id} failed: ${error.message}`);
    sendJson(response, 500, { error: error.message });
  } finally {
    await rm(temporaryDirectory, { recursive: true, force: true });
  }
}

const server = createServer((request, response) => {
  const { pathname } = new URL(request.url, `http://localhost:${port}`);

  if (request.method === "POST" && pathname === "/verify") {
    verify(request, response).catch((error) => {
      sendJson(response, 500, { error: error.message });
    });
    return;
  }

  if (request.method !== "GET" && request.method !== "HEAD") {
    sendJson(response, 405, { error: `Unsupported method: ${request.method}` });
    return;
  }

  if (pathname === "/") {
    response.writeHead(302, { Location: "/preview.html" });
    response.end();
    return;
  }

  serveFile(request, response, pathname).catch((error) => {
    console.error(`failed to serve ${pathname}: ${error.message}`);
    if (!response.headersSent) {
      sendJson(response, 500, { error: error.message });
    }
    response.end();
  });
});

server.listen(port, "127.0.0.1", () => {
  console.log(`Preview:  http://localhost:${port}/preview.html`);
  console.log(`Isolated: http://localhost:${port}/isolated/preview.html`);
  console.log("");
  console.log(
    "Set PREVIEW_URL in the bound Apps Script project to the first address to " +
      "open it from the Sheet.",
  );
});
