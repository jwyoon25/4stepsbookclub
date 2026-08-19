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

## 2026-08-19 — Phase 1, and designing around a number nobody has measured twice

Phase 1 is built end to end and the export ran in the real Sheet: the three menu
items, the Drive export, the cell highlighting, and the schema check the browser
had been going without. Four PDFs reached
`4steps PDF Builds/<book>/2026-08-19 05-30-18/` on the first attempt with
nothing adjusted.

### What shipped

The transport first, because it decided the rest. Finished PDFs travel to Drive
as ZIP archives (`58e8afd`); the 4steps menu grew **Validate workbook**, **Open
preview**, and **Create all approved PDFs**, all three opening the same window
with a different job to do (`8ec0676`); the cell a validation message names is
filled, noted, and scrolled to (`f394752`); and the JSON schemas now run in the
browser as generated code (`cb81c2b`).

The export writes to the folder the hosted renderer has always written to, by
calling `Code.gs`'s own `createBuildFolder_` rather than describing the
convention a second time, and names its files the way `lib/build.mjs` names them
on disk. A test asserts the two lists of file names are equal, because they are
defined in different files and would otherwise drift silently.

### What was measured

A full twelve-lesson export, compiled locally with the same WebAssembly compiler
the preview runs:

| | |
| --- | --- |
| PDFs a twelve-lesson book owes | 26 |
| Compiling all of them | 0.6 s |
| Raw | 4.08 MB |
| Deflated | 3.07 MB — 75.2% |
| Base64, as sent | 4.09 MB |
| Calls at the 2 MB archive budget | 2, against 26 |

The compile time is the point: 0.6 seconds against roughly three minutes of
transfer for the same work, which is why the export is designed around
`google.script.run` and not around Typst.

### What the first real export measured

Three exports of the same four PDFs, 0.60 MB, one call each, from the bound
Sheet. Apps Script reports what it spends, so the channel is the remainder:

| Stage | Run 1 | Run 2 | Run 3 | Per what |
| --- | --- | --- | --- | --- |
| `DriveApp.createFile` | **1.58 s** | **1.17 s** | **0.98 s** | each file |
| Build folder | 3.8 s | 3.1 s | 2.9 s | each export |
| Channel | 1.41 s | 1.63 s | 1.53 s | 0.66 MB of base64 |
| `Utilities.base64Decode` | 0.36 s | 0.40 s | 0.44 s | 0.66 MB of base64 |
| `Utilities.unzip` | **0.02 s** | **0.04 s** | **0.04 s** | the whole archive |
| Whole export | 12.2 s | 10.1 s | 8.9 s | |

**The transfer was never the expensive part. Drive was.** The session was spent
designing around `google.script.run`, and `google.script.run` turns out to cost
1.41 seconds of the 8.13; six and a third went to writing four files.

That does not make the archives wrong — they removed twenty-five redundant
folder resolutions and twenty-five calls, which is why a twelve-lesson book now
projects to about 50 seconds instead of 202. It makes them wrong *about what
they were for*. The remaining 36 seconds is `createFile` called twenty-six
times, and no transport change reaches it.

The build folder took 3.8 seconds after compiling had already finished,
serially, so it is now asked for first. That buys the compile time and no more —
0.12 seconds on four PDFs, under a second on a whole book — because the folder
is much the slower of the two. Worth the lines; not the saving it first looked
like.

A second and third export the same day are why that is stated so carefully. Each
came in faster than the last, and none of it was the change: `createFile` went
1.58, 1.17, 0.98 seconds a file and the folder 3.8, 3.1, 2.9. **Drive spread 62%
across three runs**, which is more than any of the optimizations considered here
would have returned, and one measurement was not enough to see it.

### The wait that was being ignored

The export happens once a book. Reading the Sheet happens after every edit, and
it is slower: 5.3, 5.4, and 10.6 seconds for a session's first read of a
*one-lesson* workbook, and 3.5 seconds for a second read in the same window.
Some of the first figure is a cold Apps Script container; 3.5 seconds is what is
left when it is warm.

Having just been caught inferring, `readWorkbookGrids` was given the same
treatment as the export: it reports flush, read, and tab count, and the window
prints script against channel. Three reads then said it outright.

| | Read 1 | Read 2 | Read 3 |
| --- | --- | --- | --- |
| `SpreadsheetApp.flush()` | 4 ms | 5 ms | 3 ms |
| `getValues()`, 7 tabs | 4.01 s | 2.81 s | 3.68 s |
| Channel | 1.38 s | 1.32 s | 1.05 s |

**`getValues` costs about half a second a tab and the data in it is irrelevant.**
The Sheet has seven tabs; the contract defines six. An eighth of every refresh
was spent fetching a tutor's notes in order to throw them away. The window now
names the tabs it wants, and the names travel from the contract rather than
being written down again in Apps Script — the adapter still knows nothing about
what a workbook is, which is the only reason it was safe to change. Four reads
afterwards put the whole refresh at 3.96 seconds against 4.75, and half a second
a tab held across all seven.

The obvious next step was dismissed too fast. `Values.batchGet` would fetch every
range in one call and would lose the type information that catches a chapter
range Google turned into a date — but `Spreadsheets.get` with `includeGridData`
returns `numberFormat.type` beside each value, which names a DATE cell outright.
The choice is a service the Sheet owner enables and a heavier response to parse,
not speed against correctness, and it was recorded as the latter for a day.

**And `google.script.run` costs about 1.25 seconds a call, almost regardless of
payload.** That is the number the whole export was designed without. It vindicates
the archives — twenty-six calls to two saves about 30 seconds of pure overhead —
and it retires the idea, entertained twice this session, of lowering the archive
budget to stay inside proven payload sizes. That would have bought nothing and
cost seconds.

### What was learned

- **The archive is a ZIP the browser writes itself.** `CompressionStream` is
  deflate in both Chrome and Node, so `builder/browser/pdf-archive.mjs` keeps
  that directory's rule of importing nothing, and the same writer is what the
  test checks. Two independent readers — JSZip and `unzip -t` — confirm the
  output, which matters because the reader that counts is Apps Script's and
  cannot be tested from here.
- **Ajv will compile itself away.** Its standalone codegen turns the two schemas
  into a 98 KB ES module needing exactly one helper, a UTF-16-aware string
  length, published as CommonJS. Inlining fifteen lines beat adding a bundler,
  and the build now refuses any *other* `require` rather than shipping a page
  that fails when someone opens it.
- **A test written for one rule found that another had overtaken it.** The
  layout budget was being checked with an over-long vocabulary excerpt; adding
  the schemas meant the schema caught it first, at a more precise path. Both
  rules now have a case that only they can fail, which took reading the schema
  to construct — every field inside its own limit, and the sum over the page's.
- **Two dialogs, one protocol.** The Phase 0 dialog reported failures as their
  own message types; the production one carries an `error` on the reply. Making
  the gate's copy agree was four lines and left one shape instead of two, and
  the eight checks and their fixtures are untouched.
- **The Chrome-only constraint held up under a second look.** Nothing in this
  session's work is a reason to revisit cross-origin isolation: the export needs
  the dialog for every call it makes, so isolation would cost more now than it
  did during the gate.

### Left open

Where the bundle is hosted is settled: a second Cloudflare Pages project over
this repository, built the same way the site is, behind Cloudflare Access. It
needs no deploy script and no `wrangler`, because the build already runs in
Cloudflare's CI on every push and wants no Typst CLI.

**Phase 1 is complete.** What is left is not decisions.

The export that ran carried one lesson. A twelve-lesson book is twenty-six files
and 4.09 MB of base64, and it is what settles the two things four files could
not: whether the projection of about 40 seconds holds, and how much one
`google.script.run` call actually carries. 0.66 MB is proven; the budget is 2 MB
and halves on refusal, so a full book finds the ceiling if there is one without
failing the export.

If 40 seconds turns out to be worth improving — and for something an author does
once a book, it may well not be — the two candidates are the advanced Drive
service in place of `DriveApp.createFile`, and several concurrent
`google.script.run` calls, since Apps Script runs a user's executions in
parallel. Both attack `createFile`, which is the only thing left that costs
anything.

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
