#!/usr/bin/env node

import { createHash, timingSafeEqual } from "node:crypto";
import { createServer } from "node:http";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { isExpectedBuildError } from "../lib/build.mjs";
import { WorkbookSheetError } from "../lib/sheet-import.mjs";
import { renderWorkbookArchive } from "./render-archive.mjs";

const DEFAULT_MAX_INPUT_BYTES = 20 * 1024 * 1024;
const XLSX_CONTENT_TYPE =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

class HttpError extends Error {
  constructor(statusCode, message) {
    super(message);
    this.name = "HttpError";
    this.statusCode = statusCode;
  }
}

function authorized(header, expectedToken) {
  const suppliedToken = header?.startsWith("Bearer ")
    ? header.slice("Bearer ".length)
    : "";
  const suppliedDigest = createHash("sha256").update(suppliedToken).digest();
  const expectedDigest = createHash("sha256").update(expectedToken).digest();
  return timingSafeEqual(suppliedDigest, expectedDigest);
}

function sendJson(response, statusCode, value) {
  const body = Buffer.from(`${JSON.stringify(value)}\n`);
  response.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": body.length,
    "Cache-Control": "no-store",
  });
  response.end(body);
}

async function readRequestBody(request, maximumBytes) {
  const declaredLength = Number(request.headers["content-length"] ?? 0);
  if (declaredLength > maximumBytes) {
    throw new HttpError(
      413,
      `Workbook exports must be ${maximumBytes} bytes or smaller.`,
    );
  }

  const chunks = [];
  let totalBytes = 0;
  for await (const chunk of request) {
    totalBytes += chunk.length;
    if (totalBytes > maximumBytes) {
      throw new HttpError(
        413,
        `Workbook exports must be ${maximumBytes} bytes or smaller.`,
      );
    }
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

function workbookIdHeader(request) {
  const value = request.headers["x-workbook-id"];
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

export function createWorkbookRenderServer({
  token,
  maxInputBytes = DEFAULT_MAX_INPUT_BYTES,
  render = renderWorkbookArchive,
} = {}) {
  if (typeof token !== "string" || token.length < 32) {
    throw new TypeError("Renderer token must contain at least 32 characters.");
  }

  return createServer(async (request, response) => {
    try {
      const url = new URL(request.url ?? "/", "http://renderer.local");
      if (request.method === "GET" && url.pathname === "/healthz") {
        sendJson(response, 200, { ok: true });
        return;
      }

      if (request.method !== "POST" || url.pathname !== "/render") {
        throw new HttpError(404, "Not found.");
      }
      if (!authorized(request.headers.authorization, token)) {
        throw new HttpError(401, "Unauthorized.");
      }

      const contentType = request.headers["content-type"]?.split(";", 1)[0];
      if (
        contentType !== XLSX_CONTENT_TYPE &&
        contentType !== "application/octet-stream"
      ) {
        throw new HttpError(415, "Request body must be an .xlsx workbook.");
      }

      const spreadsheet = await readRequestBody(request, maxInputBytes);
      const result = await render(spreadsheet, {
        workbookId: workbookIdHeader(request),
      });
      const archiveName = `${result.workbookId}-pdfs.zip`;
      response.writeHead(200, {
        "Content-Type": "application/zip",
        "Content-Length": result.archive.length,
        "Content-Disposition": `attachment; filename="${archiveName}"`,
        "Cache-Control": "no-store",
        "X-Workbook-Id": result.workbookId,
        "X-PDF-Count": String(result.pdfNames.length),
      });
      response.end(result.archive);
    } catch (error) {
      if (error instanceof HttpError) {
        sendJson(response, error.statusCode, { error: error.message });
      } else if (
        error instanceof WorkbookSheetError ||
        isExpectedBuildError(error)
      ) {
        sendJson(response, 422, { error: error.message });
      } else {
        console.error(error);
        sendJson(response, 500, { error: "Workbook rendering failed." });
      }
    }
  });
}

function startFromEnvironment() {
  const token = process.env.RENDERER_TOKEN;
  if (!token) {
    throw new Error("RENDERER_TOKEN is required.");
  }
  const port = Number(process.env.PORT ?? 8080);
  const server = createWorkbookRenderServer({ token });
  server.listen(port, "0.0.0.0", () => {
    console.log(`Workbook render service listening on port ${port}`);
  });
}

if (
  process.argv[1] &&
  resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))
) {
  startFromEnvironment();
}
