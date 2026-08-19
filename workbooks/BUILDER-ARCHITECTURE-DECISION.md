# Workbook Builder Architecture Decision

- **Status:** Accepted and validated; Phase 0 passed on 2026-08-19
- **Decision date:** 2026-08-19
- **Scope:** Staff authoring, preview, PDF generation, and Drive delivery

This record captures the agreed direction for the first workbook-builder MVP.
It complements the founder-confirmed requirements in
[`CONTENT-WORKFLOW-DECISIONS.md`](CONTENT-WORKFLOW-DECISIONS.md); it does not
change those requirements or the schema-v1 content model. What is currently true
is here; how it got here, session by session, is in
[`BUILD-LOG.md`](BUILD-LOG.md).

## Decision

Use **Google Sheets as the MVP authoring surface**, with an Apps Script launcher
and Drive bridge. Compile the workbook with Typst in the author's browser,
display the generated PDF in a separate preview window, and save approved PDFs
to Google Drive.

Keep the existing native Typst HTTP renderer working as a tested fallback, but
do not make a metered cloud renderer the default MVP dependency. Defer Payload
or another purpose-built content application until a tutor pilot demonstrates
that Google Sheets is the limiting part of the workflow.

## Why this is the best current fit

The locked workflow requires all of the following:

- Tutors never edit Typst or place page breaks.
- Tutors can paste multiple questions or vocabulary entries in one action.
- Response-space defaults are automatic but remain overridable per item.
- The system owns layout, numbering, pagination, and edition differences.
- Authors see a generated PDF before final export.
- Exports include standalone and complete-workbook PDFs in student and teacher
  editions.
- Teacher-only guidance never appears in a student PDF.

Sheets already supplies the familiar grid and bulk-paste behavior. The existing
schema, importer, Typst renderer, and PDF audits already own the publishing
rules. Running that final compilation in the browser removes the separate
renderer bill without moving layout responsibility back to the tutor.

## Target author experience

The browser windows provide the useful part of a LaTeX-style split editor while
keeping Typst hidden:

- **Left:** the Google Sheet containing workbook content and controls.
- **Right:** a separate 4steps preview window opened from the Sheet menu.
- **Refresh preview:** validates the latest cells and regenerates the selected
  PDF on demand.
- **Preview controls:** select current lesson or complete workbook and student
  or teacher edition.
- **Validation feedback:** identifies the exact tab, row, and field to fix.
- **Save approved PDFs:** writes the selected output or all required outputs to
  the workbook's build folder in Google Drive.

The MVP uses an explicit refresh rather than recompiling after every cell edit.
Automatic refresh may be considered after the pilot if it is useful and does
not make the Sheet or Apps Script quotas unreliable.

## Target architecture

```text
Google Sheet
    |
    | Apps Script reads tab values
    v
shared schema-v1 parser and validator
    |
    | normalized workbook data + bundled templates, fonts, and logos
    v
Typst WASM in the author's browser
    |
    +--> PDF preview and existing consistency audits
    |
    +--> Apps Script Drive bridge --> Google Drive build folder

Fallback: existing native Typst HTTP renderer
```

### Component boundaries

- **Authoring:** Google Sheets remains the source of tutor-authored content for
  the MVP.
- **Sheet adapters:** Node may continue reading exported `.xlsx` files, while
  Apps Script returns cell matrices directly. Both adapters feed the same pure
  parser.
- **Content contract:** the shared parser validates tab/header rules, applies
  defaults, and creates schema-v1 records. The UI must not introduce a second
  content model.
- **Rendering:** Typst templates, fonts, logos, and edition rules remain the
  only layout implementation.
- **Preview:** the browser shows the real generated PDF, not an HTML imitation.
- **Storage:** Apps Script saves approved PDFs to Google Drive one file at a
  time.
- **Fallback:** the current token-protected native renderer stays available for
  compatibility or operational recovery.

## Phase 0: mandatory compatibility gate

The preferred browser compiler is
[`typst-wasm`](https://github.com/typst-wasm/typst-wasm). The current workbook
has already compiled successfully with it outside Apps Script, passed the PDF
audit, and matched the native Typst output for the tested lesson. The remaining
risk is the real Google Apps Script HTML environment.

Apps Script HTML runs in a sandboxed iframe. The `typst-wasm` worker backend
requires cross-origin isolation, but its automatic backend may use WebAssembly
JavaScript Promise Integration (JSPI) in a compatible browser. The MVP may be
Chrome-first if this is the reliable route.

Before broader implementation, run a small spike in the actual bound Sheet and
prove all of the following:

1. Open the preview window from the 4steps Sheet menu.
2. Load the compiler, workbook templates, four brand fonts, and logo assets.
3. Compile and display a real standalone student lesson.
4. Compile and display its teacher edition.
5. Compile a representative complete workbook.
6. Transfer the largest expected PDF through Apps Script and save it to Drive.
7. Produce zero Typst diagnostics, pass the existing PDF audits, and retain
   visual parity with the native renderer.
8. Achieve a usable cold start and refresh time on the founder's actual laptop.

This gate is pass/fail. Do not build the full preview interface until the
compiler and Drive round trip succeed in the real environment.

### The gate is built

[`builder/README.md`](builder/README.md) is its runbook. Three commands carry
it: `workbook:browser-bundle` writes the compiler, templates, fonts, logos, and
representative content as static files; `workbook:browser-gate` serves them with
the headers a static host would send and audits whatever the browser produces;
`workbook:browser-verify` compares the browser compiler with the native one
without involving Google at all. `builder/apps-script/` holds the Sheet menu
item, the launcher dialog, and the Drive write.

### What the gate has already established

Measured on the example book, 2026-08-19, macOS, Node 24.16, typst-wasm 1.0.0
against the Typst 0.15.1 CLI:

| Result | Measurement |
| --- | --- |
| Workbooks compiled both ways | 4 — lesson and 12-lesson workbook, each edition |
| Pages | 162 |
| Typst diagnostics | none |
| Existing PDF audit | passed on every browser-compiled PDF |
| Text and rule parity | identical; worst positional difference 0.000 pt |
| Rasterized parity | identical; 324,641,520 channels, no differing pixel |
| Compile time, warm compiler | 130–160 ms per workbook; 6–21 ms to recompile |
| Compiler start | 56–65 ms, then 36–44 ms to load templates, fonts, and logos |
| Largest PDF | 484 KB for the 86-page complete workbook |
| Bundle a browser downloads once | 43.91 MB, 13.67 MB compressed |

Three findings the plan above did not anticipate:

- **The two Typst versions differ and the output does not.** typst-wasm 1.0.0
  embeds Typst 0.15.0 while the CLI here is 0.15.1, and every page still matches
  to the pixel. That is luck worth keeping under a test rather than a guarantee:
  `workbook:browser-verify` exists to be run whenever either version moves.
- **Cross-origin isolation and the Drive channel are mutually exclusive.** The
  worker backend needs isolation; an isolated page loses `window.opener`, which
  is the preview window's only route back to the Apps Script dialog. So the
  Drive round trip runs on JSPI, which is Chrome and Edge 137+, and the bundle
  also serves an isolated copy of the same page to establish whether a browser
  without JSPI could compile at all. The MVP being Chrome-first is now a
  consequence of the Drive channel, not of the compiler.
- **The fonts cost as much as the compiler.** The four brand faces are 21.23 MB
  raw and 5.22 MB compressed, against 22.10 MB and 8.04 MB for the engine, and
  Gowun Batang is three quarters of the font weight. Both are cached after the
  first load. `engine.core.wasm` is 21.7 MiB, under Cloudflare Pages' 25 MiB
  per-file limit, but not by much.

### Phase 0 gate run — 2026-08-19

Run from the bound Sheet on the founder's laptop, Chrome 151 on macOS, against
the example book served from the local gate server. **All eight checks passed.**

| # | Check | Result |
| --- | --- | --- |
| 1 | Open the preview window from the Sheet menu | passed; the dialog and the window kept an opener relationship |
| 2 | Load the compiler, templates, fonts, and logos | passed; 21.67 MB on the JSPI backend |
| 3 | A standalone student lesson compiles and displays | passed; 0.13 MB in 137 ms |
| 4 | Its teacher edition compiles and displays | passed; 0.13 MB in 26 ms |
| 5 | A representative complete workbook compiles | passed; 0.47 MB in 168 ms student, 96 ms teacher |
| 6 | The largest PDF reaches Drive through Apps Script | passed; 0.47 MB saved in 7.78 s |
| 7 | Zero diagnostics, audits pass, parity with native | passed; all four workbooks audited and identical to the native renderer |
| 8 | A usable cold start and refresh | passed; 164 ms cold, 21 ms to refresh |

The browser reported `jspi`, no cross-origin isolation, and no shared memory —
exactly the combination the transport was designed around. The compiler was
Typst 0.15.0 throughout, and the parity comparison was made against the 0.15.1
CLI on the same machine.

Three things this settles that the analysis above could only predict:

- **An Apps Script dialog may open a window and keep talking to it.** The
  sandboxed iframe permits the popup, the opener survives, and the two windows
  exchanged the workbook and the finished PDF across origins without help.
- **`google.script.run` carries a complete workbook.** 0.47 MB of PDF, base64
  encoded, in a single call. It is also the slowest step in the whole system by
  two orders of magnitude: 7.78 seconds, against 168 milliseconds to compile the
  same document. Phase 1's "create all approved PDFs" writes 26 files for a
  twelve-lesson book, so that is roughly three minutes of transfer, and it is
  the number to design around rather than the compile time.
- **The cold start is not the problem the size suggested.** 164 milliseconds
  here, 374 on the first ever load. Both are localhost figures and both exclude
  the download that a hosted bundle would pay once; what they establish is that
  nothing in the compiler's own startup is slow.

## Implementation phases

### Phase 1: production MVP

1. Extract the row-to-schema logic from the `.xlsx` reader into a browser-safe,
   pure shared module.
2. Keep a Node/Excel adapter for the existing command-line and HTTP paths.
3. Add an Apps Script adapter that supplies raw Sheet matrices to the preview.
4. Add a browser compiler adapter that loads all Typst sources, data, fonts, and
   images into the in-memory compiler.
5. Add **Validate workbook**, **Open preview**, and **Create all approved PDFs**
   to the 4steps menu.
6. Show exact Sheet locations for validation and compilation errors.
7. Save PDFs to the existing timestamped Drive folder convention.
8. Keep the native renderer behind a clearly identified fallback path.

### Phase 2: tutor pilot

Use the builder for at least two real workbooks with the founder and one or two
tutors. Record:

- Time required to create a lesson and a complete workbook.
- Validation failures and the cells that caused them.
- Difficulty navigating the wide question and vocabulary tabs.
- How frequently authors refresh the preview.
- Whether revisions, approvals, permissions, or content reuse are genuinely
  required.

Add only improvements supported by the pilot, such as row-level status,
current-lesson filters, quick-add rows, clearer error highlighting, or preview
shortcuts.

### Phase 3: custom-builder decision

Reconsider Payload or a purpose-built web builder only if repeated use shows
several of these needs:

- Multiple simultaneous authors.
- Role-based permissions or approval workflows.
- Operationally necessary revision history.
- Search and reuse across a large curriculum library.
- Persistent tutor difficulty with spreadsheet navigation.
- Recurring content errors that Sheet validation cannot reasonably prevent.

If a custom builder is justified, it must continue writing the same schema-v1
content boundary and using the same Typst rendering and audit layer. Replacing
the editor must not trigger a workbook-design rewrite.

## Fallback order

If the Phase 0 gate fails, investigate alternatives in this order:

1. Test [`typst.ts`](https://github.com/Myriad-Dreamin/typst.ts) in the same
   Apps Script environment and require native-output parity before adoption.
2. If strictly zero metered cloud compute remains mandatory, package the native
   Typst renderer as a local desktop helper, accepting the installation and
   Sheet/Drive round-trip tradeoff.
3. If one-click reliability becomes more important than eliminating metered
   compute, deploy the existing native renderer with explicit budgets, alerts,
   request limits, and the current authentication token.

## Alternatives considered

### Current Sheets plus hosted native renderer

This is the fastest deployable path because it already exists and uses the
official Typst CLI plus the complete audit pipeline. It remains the reliability
fallback. It is not the preferred MVP because it requires a separately hosted,
potentially billable service and does not yet provide preview before export.

### Payload or another custom application

Payload can eventually provide structured forms, authentication, revisions,
custom components, and a polished integrated preview. It also introduces an
application host, database, storage, authentication operations, and much more
builder code. That is premature before the Sheet content contract has been
tested by real tutors.

### Typst.app and self-hosted Typst source editors

These tools provide excellent source-editor/preview experiences for developers
who know Typst. They are appropriate for internal template development, not
tutor authoring, because they expose the exact markup and project files that the
locked authoring boundary hides.

### Generic Typst HTTP APIs

[`slashformotion/typst-http-api`](https://github.com/slashformotion/typst-http-api)
is archived, warns against production use, and does not support the external
project assets required by this workbook. It is rejected.

[`tweedegolf/typst-webservice`](https://github.com/tweedegolf/typst-webservice)
is the most relevant server-side open-source alternative found. It supports
preloaded templates, assets, fonts, JSON input, and batch PDF archives. It does
not replace the 4steps Sheet importer, schema rules, authentication, build
planning, or PDF audits, so rewriting the existing service around it has little
MVP value.

### Baserow, Directus, Airtable-like tools, and other CMS products

These may improve record management, but they still require hosting and custom
preview/render integration. They provide no decisive MVP advantage over the
Sheet that authors already know. Revisit them only if the pilot proves that
Sheets itself is the problem.

### Google Docs template generation

This is rejected because it weakens deterministic pagination, typography,
student/teacher separation, workbook variants, and the existing audit
guarantees.

## Billing and reliability position

The selected architecture is designed to have **no billable PDF-compute path
and no surprise usage-based renderer charges**:

- Compilation uses the author's browser CPU.
- Apps Script performs bounded Sheet and Drive operations.
- Compiler and brand assets may be served as static files without server-side
  functions.
- The Cloud Run/native renderer is not part of the default path.

This is not a promise that Google, a static host, or another provider will never
change its free quotas or terms. Apps Script limits can stop a build, and static
hosting can impose deployment limits. The architecture deliberately turns those
conditions into availability errors rather than automatic PDF-compute charges.

## Upstream technical references

- [Apps Script HTML iframe restrictions](https://developers.google.com/apps-script/guides/html/restrictions)
- [Apps Script client/server communication](https://developers.google.com/apps-script/guides/html/communication)
- [Apps Script Drive service](https://developers.google.com/apps-script/reference/drive)
- [Apps Script quotas](https://developers.google.com/apps-script/guides/services/quotas)
- [`typst-wasm` browser deployment requirements](https://typst-wasm.github.io/typst-wasm/packages/typst-wasm/deployment/browser-requirements/)
- [Cloudflare Pages static-asset pricing](https://developers.cloudflare.com/pages/functions/pricing/)
- [Cloudflare Pages custom headers](https://developers.cloudflare.com/pages/configuration/headers/)

## Phase 1 progress

| Step | State |
| --- | --- |
| 1. Row-to-schema logic in a browser-safe shared module | done — `builder/browser/sheet-contract.mjs` |
| 2. A Node adapter over it for the command line and service | done — `lib/sheet-import.mjs` is now only the `.xlsx` half |
| 3. An Apps Script adapter supplying raw Sheet matrices | done — `builder/apps-script/SheetGrids.gs` |
| 4. A browser compiler adapter loading sources, data, fonts, images | done in Phase 0 |
| 5. **Validate workbook**, **Open preview**, **Create all approved PDFs** menu items | done — `builder/apps-script/WorkbookBuilder.gs` |
| 6. Exact Sheet locations for validation and compilation errors | done — the named cell is filled, noted, and scrolled to |
| 7. Save PDFs to the timestamped Drive folder convention | done — `builder/apps-script/WorkbookExport.gs`, through `Code.gs`'s own `createBuildFolder_` |
| 8. The native renderer behind a clearly identified fallback path | unchanged, still tested, and now named as such in the menu |

The response-space defaults, the layout budgets, and the wrapping limit moved to
`builder/browser/content-rules.mjs` alongside the contract, so a preview applies
what a disk build applies. `lib/content.mjs` keeps the filesystem; the JSON
schemas are now applied on both sides.

**Every step of Phase 1 is built, and the export has run in the real Sheet**, on
2026-08-19: four PDFs into
`4steps PDF Builds/<book>/2026-08-19 05-30-18/`, first attempt, nothing
adjusted. The three menu items, the archive transfer, the build folder, and the
cell marking all work against Google. What has not been run is a full
twelve-lesson book; the projection below is from the four-file run.

### How the export is designed, and what it actually costs

The transfer, not the compiler, is what the export had to be designed around:
7.78 seconds for one 0.47 MB PDF against 168 milliseconds to compile it. Sending
a twelve-lesson book's twenty-six files one at a time is about three and a half
minutes.

They travel as ZIP archives. `Utilities.unzip` already splits the hosted
renderer's archives on the Apps Script side, so the format is proven rather than
assumed, and workbook PDFs deflate to about three quarters of their size —
4.08 MB of PDF for a twelve-lesson book, 3.07 MB compressed, 4.09 MB once base64
encoded. The build folder is created once, before any bytes move, so a run that
fails partway leaves one timestamped folder holding what arrived.

#### The wait an author actually pays, and what a call costs

The export happens once a book. **Reading the Sheet happens after every edit**,
and it is slower. Three reads of a *one-lesson* workbook, measured from inside:

Seven reads of a *one-lesson* workbook, measured from inside — three before the
window began naming the tabs it wants, four after:

| | 7 tabs, n=3 | 6 tabs, n=4 |
| --- | --- | --- |
| `SpreadsheetApp.flush()` | 4 ms | 3 ms |
| `getDataRange().getValues()` | 3.50 s | 2.88 s |
| — per tab | 0.50 s | 0.48 s |
| Channel | 1.25 s | 1.07 s |
| Whole read | 4.75 s | **3.96 s** |

Half a second a tab holds across all seven reads, and the one skipped tab
returned 0.80 seconds against 0.50 predicted. Individual reads spread 86%, so
nothing here means anything from one sample.

Two things fall out of this, and both were being guessed at before:

- **`getValues` costs about half a second a tab, whatever is in it.** Flushing
  is free and the data is tiny; the cost is one round trip per tab. The Sheet
  had seven tabs and the contract defines six, so an eighth of every refresh was
  fetching a tutor's notes in order to discard them. The window now names the
  tabs it wants — the names come from the contract, which runs there, so the
  script still knows nothing about what a workbook is.
- **`google.script.run` costs about 1.25 seconds a call and barely notices the
  payload.** The same channel carried 0.66 MB of base64 in ~1.5 seconds. That is
  the number the archive design needed and never had: the cost really is the
  call count, so batching twenty-six files into two calls saves about 30 seconds
  of pure overhead, and a *smaller* archive budget would have cost several
  seconds for nothing. The 2 MB budget stays.

What is left of the refresh is 2.9 seconds of `getValues` and 1.1 of channel.
The one remaining candidate is the Sheets advanced service, and the first look
at it was wrong. `Values.batchGet` does fetch every range in one call and does
return values without their types, which would lose the check that catches a
chapter range Google turned into a date. But `Spreadsheets.get` with
`includeGridData` returns `effectiveFormat.numberFormat.type` alongside each
value, which names a DATE cell outright — the same fact `instanceof Date` is
standing in for today, carried explicitly.

So the trade is not speed against correctness. It is **one API call, about 1.6
seconds a refresh instead of 4.0**, against a service the Sheet owner has to
enable, a heavier response to parse, and a date check re-expressed against a
different signal. That last part is the risk worth naming: it cannot be tested
from this repository, only in a bound Sheet.

#### Where the 7.78 seconds went — measured 2026-08-19

Three exports of the same four PDFs, 0.60 MB, in one call each. Apps Script
returns what it spends, so the channel is what is left over:

| Stage | Run 1 | Run 2 | Run 3 | Per what |
| --- | --- | --- | --- | --- |
| `DriveApp.createFile` | **1.58 s** | **1.17 s** | **0.98 s** | each file |
| Build folder | 3.8 s | 3.1 s | 2.9 s | each export |
| Channel | 1.41 s | 1.63 s | 1.53 s | 0.66 MB of base64 |
| `Utilities.base64Decode` | 0.36 s | 0.40 s | 0.44 s | 0.66 MB of base64 |
| `Utilities.unzip` | **0.02 s** | **0.04 s** | **0.04 s** | the whole archive |
| Whole export | 12.2 s | 10.1 s | 8.9 s | |

**Drive spreads 62% across three runs and it fell every time**, which is more
than any remaining optimization would return. Whether that is warming or luck
needs more runs than three; either way, nothing measured here means anything
from a single run.

**The transfer was never the expensive part; Drive was.** Unzipping four PDFs
costs twenty milliseconds and writing them costs six and a third seconds. This
overturns the assumption the design was built on — that the number of calls was
the cost — and it changes what is worth optimizing:

- **Archives were still the right move**, but for a different reason than
  expected. They removed twenty-five redundant folder resolutions and twenty-five
  calls' worth of channel, taking a twelve-lesson book from a projected 202
  seconds to a projected **40**, anywhere between 30 and 50.
- **Nothing about the transport can improve the remaining 25 to 41 seconds**,
  because it is `createFile` called twenty-six times. Only two things could: the
  advanced Drive service, which is often faster than `DriveApp`, or several
  concurrent `google.script.run` calls, since Apps Script will run a user's
  executions in parallel. Neither is worth doing before a full book has been
  exported once and the projection confirmed.
- **The folder is now requested before the compiling rather than after it**,
  which is worth the compile time and no more: 0.12 seconds on four PDFs, under
  a second on a whole book. The folder is much the slower of the two, so
  overlapping them cannot recover it.
- **How much one call carries is still unestablished.** 0.66 MB of base64 is now
  proven; the 2 MB budget stays where it is because a refused call halves it and
  repacks, so a full book's first export finds the ceiling if there is one. The
  four-file run cannot separate per-call overhead from throughput — both are
  inside that 1.41 seconds — so a full book is also what settles whether fewer,
  larger archives are worth anything.

### What Phase 1 decided

- **The browser validates against the JSON schemas.** Ajv generates its
  validating code ahead of time, so `workbook:browser-bundle` writes a
  `schema-validators.mjs` with no library behind it and the schemas stay the only
  description of the rules. This was optional while Node did every export; it
  stopped being optional when the browser became the export path. The generated
  code needs one CommonJS helper, a UTF-16-aware string length, which the module
  carries its own copy of; the build fails rather than shipping a page that needs
  anything else.
- **Approval is not a Sheet value.** "Create all approved PDFs" builds everything
  the workbook owes, and approval is the author's judgement made at the preview.
  `CONTENT-WORKFLOW-DECISIONS.md` leaves approval mechanics unsettled, and the
  `Status` column stays a note between the people working on the book. Row-level
  status remains a Phase 2 question for the pilot to answer.

### What Phase 1 still has to decide

- **Where the bundle is hosted.** The gate ran from `localhost`. The generated
  `_headers` file is ready for Cloudflare Pages, and the measured cold start
  excludes the one-time download a hosted bundle pays. Nothing else in Phase 1
  is blocked on it, and nothing after Phase 1 can start without it.
