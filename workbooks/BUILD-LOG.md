# Workbook Build Log

Dated entries recording how the workbook system got to where it is: what a
working session shipped, what it measured, and what it learned the hard way.

This is deliberately not a decision record. What is currently true lives in
[`DESIGN-DECISIONS.md`](DESIGN-DECISIONS.md),
[`CONTENT-WORKFLOW-DECISIONS.md`](CONTENT-WORKFLOW-DECISIONS.md), and
[`BUILDER-ARCHITECTURE-DECISION.md`](BUILDER-ARCHITECTURE-DECISION.md), and how
to run things lives in the READMEs. An entry here points at those rather than
restating them; what it adds is the sequence, the measurements taken on the day,
and the findings that would otherwise survive only in commit messages.

Newest first.

---

## 2026-08-19 — The browser compiler, and the content layer under it

Phase 0 of the builder architecture passed, and Phase 1 got half built. Fourteen
commits, `00520ad` through `5fc2ef3`. Session record with the full numbers:
<https://claude.ai/code/artifact/7fbe8f3e-23c3-4787-aed0-df6593901e53>.

### What shipped

The gate and everything it needed: a deployable static bundle of the compiler,
templates, fonts, and logos (`00520ad`); a local gate server that audits and
compares whatever the browser produces (`dbdbdf8`); the Apps Script launcher and
Drive bridge (`59d913e`); a verification harness comparing both renderers page by
page and pixel by pixel (`a86e6c9`); the runbook (`c5826fd`); and a one-click run
that answers all eight checks in the decision record's own order (`0285742`).

Then the content layer was pulled apart so a preview and a disk build cannot
describe a workbook differently. The Sheet contract left the `.xlsx` reader
(`6604252`), the response-space defaults and layout budgets left the filesystem
loader (`d103b0c`), build targets got one description (`6fb277f`), and the
preview window started compiling the live Sheet (`11fba20`).

| Moved | Before | After | What it owns now |
| --- | --- | --- | --- |
| `lib/sheet-import.mjs` | 684 | 201 | the `.xlsx` half only |
| `lib/content.mjs` | 407 | 208 | the filesystem and the JSON schemas |
| `builder/browser/*.mjs` | — | 1885 | tabs and columns, defaults and budgets, targets, the compiler adapter |

The four `builder/browser` modules import nothing at all. Node imports them, the
preview window fetches them, and `npm test` went from 41 tests to 60.

### What the gate measured

All eight checks passed from the bound Sheet on Chrome 151, recorded in full in
the decision record. The compiler is not the interesting number: a lesson
compiles in 137 ms and an 86-page workbook in 168 ms, cold start is 164 ms, and
a refresh is 21 ms. Four representative workbooks — 162 pages — came out
identical to the native renderer across 324,641,520 rasterized channels with no
differing pixel and no Typst diagnostic.

The interesting number is 7.78 seconds, which is what one 0.47 MB PDF took to
reach Drive through `google.script.run`.

### What was learned

- **The two Typst versions differ and the output does not.** typst-wasm 1.0.0
  carries Typst 0.15.0 against the CLI's 0.15.1. `npm run workbook:browser-verify`
  exists to be run whenever either moves.
- **Chrome-first is the Drive channel's fault, not the compiler's.** The worker
  backend needs cross-origin isolation, and an isolated page loses
  `window.opener`, which is the preview's only route back to the dialog. The
  round trip therefore runs on JSPI. The isolated copy of the page ships anyway,
  because it establishes that a browser without JSPI can still compile.
- **The transfer is the bottleneck.** 7.78 s against 168 ms to compile the same
  document; 26 files for a twelve-lesson book is about three minutes. The export
  has to be designed around that, not merely wired up.
- **The fonts cost about what the compiler costs.** 21.23 MB raw and 5.22 MB
  compressed for four faces, against 22.10 MB and 8.04 MB for the engine, and
  `engine.core.wasm` is 21.7 MiB against Cloudflare Pages' 25 MiB per-file limit.
- **A test found unreachable code the same day it was written.** The preview
  checked teacher editions for answer guidance that the Sheet contract already
  requires cell by cell. The test meant to prove the check worked proved it could
  never fire, and it was removed.
- **Two traps worth remembering**, both now in
  [`builder/README.md`](builder/README.md): the script editor opens on a Drive
  error page when more than one Google account is signed in, and typst-wasm ships
  a bundler plugin in its runtime dependencies.

### Left open

The browser does not validate against the JSON schemas, which mattered little
while Node did every export and matters more as the browser becomes the export
path. Where the bundle is hosted is undecided; the gate ran from `localhost`, so
the cold start above excludes the download a hosted bundle pays once. Phase 1
still needs its three menu items, the Drive build-folder convention, and cell
highlighting for the errors it already names.
