// ---------------------------------------------------------------------------
// The browser compiler, running under Node.
//
// The preview page and this module load the same templates, fonts, and logos
// through the same adapter; only the transport differs — `fetch` there, the
// filesystem here. That is what makes a local check meaningful: what this
// verifies is the code the browser runs, not a Node-shaped imitation of it.
// ---------------------------------------------------------------------------

import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { createTypstCompiler, selectAutomaticBackendKind } from "typst-wasm";
import { createWorkerThread } from "typst-wasm/worker/node";

import { loadWorkbookProject } from "../builder/browser/workbook-compiler.mjs";

const moduleDirectory = dirname(fileURLToPath(import.meta.url));
const workbooksRoot = resolve(moduleDirectory, "..");

const ENGINE_CORE_MODULES = [
  "engine.core.wasm",
  "engine.core2.wasm",
  "engine.core3.wasm",
];

export class TypstCompilerError extends Error {
  constructor(message, options) {
    super(message, options);
    this.name = "TypstCompilerError";
  }
}

function workerFactory() {
  // Node's Worker rejects a bare `file://` string, so the resolved specifier is
  // handed over as a URL.
  return createWorkerThread(
    new URL(import.meta.resolve("typst-wasm/worker/worker-thread")),
  );
}

/**
 * Create a compiler with the whole workbook project already loaded.
 *
 * Returns the compiler, the backend it chose, and how long each stage took, so
 * a local run reports the same measurements the gate asks the browser for.
 */
export async function createWorkbookTypstCompiler() {
  const backend = selectAutomaticBackendKind({ worker: workerFactory });
  if (backend === "none") {
    throw new TypstCompilerError(
      "This Node build offers neither shared memory nor JSPI, so typst-wasm " +
        "cannot run. Node 20 or newer is required.",
    );
  }

  const startedAt = Date.now();
  const coreModules = Object.fromEntries(
    ENGINE_CORE_MODULES.map((name) => [
      name,
      readFile(fileURLToPath(import.meta.resolve(`typst-wasm/engine/${name}`))).then(
        (bytes) => WebAssembly.compile(bytes),
      ),
    ]),
  );

  const compiler = await createTypstCompiler({
    coreModules,
    worker: workerFactory,
  });
  const readyAt = Date.now();

  const project = await loadWorkbookProject(compiler, {
    readText: (path) => readFile(resolve(workbooksRoot, path), "utf8"),
    readBytes: async (path) => new Uint8Array(await readFile(resolve(workbooksRoot, path))),
  });

  return {
    compiler,
    backend,
    readyMilliseconds: readyAt - startedAt,
    projectMilliseconds: Date.now() - readyAt,
    projectBytes: project.bytes,
  };
}
