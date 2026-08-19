# The workbook builder's browser side

Google Sheets is the authoring surface, Typst compiles the workbook **in the
author's browser**, the real PDF is previewed before export, and approved PDFs
reach Drive through Apps Script.
[`../BUILDER-ARCHITECTURE-DECISION.md`](../BUILDER-ARCHITECTURE-DECISION.md)
records why, and demanded one thing before any of it was built: proof that the
compiler and the Drive round trip work inside Google. They do — the Phase 0 gate
passed on 2026-08-19, and the runbook below still reproduces it.

What is here now is that gate plus the builder itself: three menu items, the
content contract they run, and the Drive export they finish with.

```text
builder/
├── browser/                   # runs in the preview window; imports nothing but itself
│   ├── sheet-contract.mjs     # which tabs exist, and how a row becomes schema-v1 content
│   ├── content-rules.mjs      # response-space defaults, layout budgets, schema failures
│   ├── build-targets.mjs      # what can be previewed or exported, and the bundle for it
│   ├── workbook-compiler.mjs  # which files make a compilable project, and how to load them
│   ├── pdf-archive.mjs        # how finished PDFs are packed for the trip to Drive
│   ├── preview.html           # the workbook window
│   ├── preview.mjs            # environment probe, Sheet read, compile, display, export
│   └── preview.css
└── apps-script/
    ├── SheetGrids.gs                # reads every tab as a grid of cells
    ├── SheetHighlights.gs           # marks the cell a validation message names
    ├── WorkbookBuilder.gs           # the three menu items and the window they open
    ├── WorkbookBuilderDialog.html   # the dialog the window answers to
    ├── WorkbookExport.gs            # unpacks archives into the Drive build folder
    ├── Phase0.gs                    # the gate's own menu item and Drive write
    └── Phase0Dialog.html            # the gate's dialog
```

The five `browser/` modules are the content contract. Node imports the same
files — the `.xlsx` importer, the disk loader, and the verification harness all
go through them — so a preview and a real build cannot describe the workbook
differently. A sixth module, `schema-validators.mjs`, is generated into the
bundle from `workbooks/schema/*.json` when it is built; see
[Validation](#validation) below.

## What is already proven, without Google

Run this from the repository root:

```bash
npm run workbook:browser-verify
```

It compiles every representative workbook twice — once with the WebAssembly
compiler the preview page uses, once with the Typst CLI the production build
uses — audits the WebAssembly output with the existing workbook audit, and
compares the two renderings by every text run and response rule and then pixel
by pixel. `npm test` runs a shorter version of the same check.

On the example book, all four workbooks are identical to the native renderer,
down to the pixel. The measured results are recorded in the decision record.

What this cannot answer is what Google's own environment allows. That is the
whole of what the gate below adds.

## Running the gate

### 1. Build the bundle

```bash
npm run workbook:browser-bundle
```

This writes `workbooks/output/browser-bundle/`: the compiler, the workbook
templates, the four brand fonts, the logo set, and representative workbook
content, as ordinary static files. To use a real book instead of the example
package:

```bash
npm run workbook:browser-bundle -- workbooks/content/the-book-id/workbook.json
```

The command prints what a browser has to download. The bundle is deployable to
any static host as-is, including the `_headers` file Cloudflare Pages needs.

### 2. Serve it

```bash
npm run workbook:browser-gate
```

This serves the bundle on `http://localhost:8787` with the headers a static host
would send, and adds one endpoint the browser cannot provide for itself:
**Audit and compare with native** sends the PDF the browser just produced back
for the real workbook audit and a page-by-page comparison against the Typst CLI.

Two addresses are served:

| Address | Compiler backend | Drive |
| --- | --- | --- |
| `/preview.html` | JSPI — Chrome or Edge 137+ | yes |
| `/isolated/preview.html` | worker — any current browser | no |

The second is cross-origin isolated, which is what buys the worker backend in a
browser without JSPI. Isolation also severs `window.opener`, which is the only
channel back to the Apps Script dialog, so that copy can compile and preview but
cannot save. Use the first address for the full gate and the second to find out
whether a browser without JSPI could compile at all.

### 3. Connect the Sheet

In the workbook's bound Apps Script project:

1. Add every `apps-script/` file above as a new file, keeping those exact names.
   The two `.html` files are loaded by name, and `Code.gs` looks for the others
   by function name.
2. Replace `Code.gs` with this repository's copy, which adds the menu items.
3. Optionally set a `PREVIEW_URL` script property. The default is
   `http://localhost:8787/preview.html`.

`Phase0.gs` and `Phase0Dialog.html` are only needed to reproduce the gate.
Everything else is the builder, and `WorkbookExport.gs` calls `Code.gs`'s own
`createBuildFolder_` rather than describing the Drive convention twice.

If **Extensions → Apps Script** lands on a Google Drive page saying the file
cannot be opened, the editor opened under a different signed-in Google account
than the one that owns the Sheet. Match the account index in the Sheet's own URL
— `docs.google.com/spreadsheets/u/1/d/…` needs `script.google.com/u/1/home` — or
use a window where the owning account is the only one signed in. Apps Script has
never handled multiple accounts well.

No new OAuth scopes: the Sheet UI and Drive scopes the renderer automation
already requests are enough, and the browser — not the script — fetches the
compiler.

### 4. Run the eight checks

Reload the Sheet, choose **4steps → Browser compiler gate (Phase 0)**, click
**Open the preview window**, and click **Run every gate check**.

That compiles all four workbooks, audits each one, compares each with native
Typst, saves the largest to Drive, and fills in a verdict for every check. The
individual controls are still there for repeating one of them by hand.

| # | Check | Where its answer comes from |
| --- | --- | --- |
| 1 | The preview window opens from the Sheet menu | The dialog answers the window, which reports the connection |
| 2 | Compiler, templates, four fonts, and logos load | The preview reports each stage as it happens |
| 3 | A real standalone student lesson compiles and displays | Compiled and shown in the viewer |
| 4 | Its teacher edition compiles and displays | Compiled and shown in the viewer |
| 5 | A representative complete workbook compiles | The 12-lesson workbook, both editions |
| 6 | The largest expected PDF reaches Drive | The largest of the four is sent through the dialog |
| 7 | Zero diagnostics, audits pass, native parity holds | The compile refuses any diagnostic; the gate server audits and compares |
| 8 | Cold start and refresh are usable | Measured from the first load and from recompiling |

The dialog also reports what the Apps Script iframe itself offers — shared
memory, JSPI, cross-origin isolation. That answers whether a future version
could compile inside the dialog instead of a separate window.

### 5. Record the result

Click **Copy the results table** in the preview window and paste it into
[`../BUILDER-ARCHITECTURE-DECISION.md`](../BUILDER-ARCHITECTURE-DECISION.md)
under Phase 0 results, together with the dialog's environment probe.

The gate is pass/fail. If every check passes, change the record's status and
start Phase 1. If any fails, the record's fallback order says what to try next,
in order.

## The three menu items

The 4steps menu offers **Validate workbook**, **Open preview**, and **Create all
approved PDFs**. All three open the same window with a different job to do,
because the workbook only exists in one place: the author's browser, where the
compiler and the content contract both run. Apps Script hands over the cells and
receives what comes back.

The dialog has to stay open. It is the window's only route to Google, and
closing it strands an export halfway.

A window opened this way reads the workbook the author is actually editing. The
dialog asks Apps Script for every tab as a grid of cells and forwards them; the
window parses them with the same contract the `.xlsx` importer uses and offers
one target per lesson and edition plus the complete workbook. **Refresh from the
Sheet** reads it again.

"Approved" is the author's judgement, made by looking at the preview before
choosing the third item. Nothing in the Sheet records it. Approval mechanics are
explicitly unsettled in
[`../CONTENT-WORKFLOW-DECISIONS.md`](../CONTENT-WORKFLOW-DECISIONS.md), and the
`Status` column on every tab is a note between the people working on the book,
not an input to anything.

### Validation

Four sets of rules run, in the order a disk build runs them:

| Rule | Where it lives | What it catches |
| --- | --- | --- |
| The Sheet contract | `sheet-contract.mjs` | missing tabs, renamed columns, a required cell left blank, a chapter range Google turned into a date |
| The JSON schemas | `workbooks/schema/*.json` | a prompt too long, a seventh guidance line, anything the content model forbids |
| The wrapping limit | `content-rules.mjs` | an unbroken run of characters no column can break |
| The layout budgets | `content-rules.mjs` | content that fits the schema and still cannot fit the page |

Every failure names a tab, a row, and a column — `"Lessons" row 5, Chapter or
page range must contain text.` — and the Sheet is then made to show it: the cell
is filled, the message becomes its note, and the Sheet scrolls to it. The mark
is undone when the workbook next parses, and it is remembered rather than
searched for, so an author's own colouring is left alone.

The schemas run in the browser as generated code. Ajv is a Node library, but it
compiles validators ahead of time, so `npm run workbook:browser-bundle` writes
`schema-validators.mjs` into the bundle and nothing loads a validation library
at runtime. Edit the schemas; never that file.

### The export

**Create all approved PDFs** compiles everything the workbook owes — one PDF per
lesson and one for the whole book, in both editions — and writes them to
`<the Sheet's folder>/4steps PDF Builds/<book title>/<timestamp>/`, which is
where the hosted renderer has always written. The file names are the ones
`lib/build.mjs` writes on disk, so a folder built either way holds the same
files.

The transfer is the whole of the design. The Phase 0 gate measured 7.78 seconds
for one 0.47 MB PDF through `google.script.run` against 168 milliseconds to
compile it, so twenty-six files sent one at a time is about three minutes. They
travel as ZIP archives instead — two calls for a twelve-lesson book, and a
quarter fewer bytes, because workbook PDFs deflate to about three quarters of
their size. `Utilities.unzip` splits them on the Apps Script side, exactly as it
already splits the hosted renderer's archives.

Two things follow from not yet knowing how much one call will carry. The archive
budget starts at 2 MB and halves if a call is refused, so the first export to
meet a real limit finds it, says so in the log, and finishes anyway. And Apps
Script returns what it spent decoding, unzipping, and writing, so the log
separates the time Drive costs from the time the channel costs. Both numbers
belong in [`../BUILD-LOG.md`](../BUILD-LOG.md) after the first real export.

## Hosting the bundle

The bundle is static files and Cloudflare Pages already serves this repository,
so it is a **second Pages project over the same repository**, built the same way
the site is:

| | Website | Builder |
| --- | --- | --- |
| Build command | `npm run build` | `npm run workbook:browser-bundle` |
| Output directory | `website/dist` | `workbooks/output/browser-bundle` |

Nothing else is needed. There is no deploy script and no `wrangler` dependency,
because the build runs in Cloudflare's own CI on every push, and it needs no
Typst CLI — the bundle omits the native version from `build-info.json` when
Typst is absent and is otherwise identical. `_headers` is generated with it, so
the isolated page keeps its cross-origin isolation and the compiler and fonts
keep their immutable cache rules.

Two things it will not survive. Every file has to stay under Cloudflare's 25 MiB
limit, which `engine.core.wasm` is 3.26 MiB away from; the bundle build refuses
rather than letting a `typst-wasm` release discover it at deploy time. And the
paths are root-absolute — `/vendor/…`, `/build-targets.mjs`, `/isolated/…` — so
the bundle has to be the root of its own hostname. It cannot be a folder inside
the public site.

### Signing in

The bundle carries the whole Typst design system, the brand logo set, and an
example book, so it sits behind **Cloudflare Access** rather than on the open
web. Access is free for a small team and authenticates against Google, which is
the account the author is already signed in to.

**Sign in once in an ordinary tab before using the Sheet menu.** Access answers
an unauthenticated request with a redirect to its own login, and the preview
window is opened by the Apps Script dialog, which the window has to keep talking
to — a login page that sets `Cross-Origin-Opener-Policy` on the way past would
sever that channel for good, and the preview would report "no opener" and refuse
to save. Arriving with the cookie already set means no redirect happens at all.
The cookie lasts as long as the Access session policy says, so this is once a
day or once a month, not once a sitting.

If the preview ever does report no opener immediately after signing in, that is
this failure and not a bug in the page.

### Pointing the Sheet at it

Set a `PREVIEW_URL` script property in the bound Apps Script project to
`https://<the hostname>/preview.html`. That is the only place the address
appears; nothing in this repository hardcodes a hostname, and the default stays
the local gate server so the runbook above keeps working.

Two things to decide before the first deploy. The Pages project needs a branch
to build from, and this work is on `workbook-production-audit` rather than
`main`. And if the hostname is `admin.<domain>`, be aware the public site
already serves the Decap CMS at `<domain>/admin/`; they are different tools with
one name between them.

## Known constraints

- **The Drive round trip needs JSPI**, which means Chrome or Edge 137 or newer.
  Any browser that gives the worker backend has been made cross-origin isolated,
  and isolation is what severs the channel to the dialog. A browser with neither
  cannot compile at all; the preview says so rather than failing obscurely.
- **`http://localhost` is fine for the gate** because opening a window is a
  top-level navigation, not a subresource. Hosting the bundle behind HTTPS is a
  Phase 1 decision, and the generated `_headers` file is there for it.
- **The two Typst versions are not identical.** typst-wasm 1.0.0 carries Typst
  0.15.0; the CLI here is 0.15.1. Their output matches exactly today, which is
  why `npm run workbook:browser-verify` exists: run it after either version
  changes.
- **The cold start is dominated by the fonts and the engine**, not by the
  workbook. Both are cached after the first load, and the bundle's cache headers
  say so.
- **`typst-wasm` declares a build plugin as a runtime dependency.**
  `tsdown-plugin-worker` is in its `dependencies`, so installing it pulls a
  bundler toolchain into the lockfile that nothing at runtime imports. It is a
  devDependency here and the browser never sees it, so the cost is install time
  and lockfile noise. Worth an upstream issue, and worth remembering before
  concluding that the compiler itself is heavy.

## Retiring the gate

Phase 0 passed on 2026-08-19 and this directory is no longer a spike: the
`browser/` modules are the content contract, and `lib/sheet-import.mjs` and
`lib/content.mjs` import them. The gate is still reproducible, and when keeping
it stops being worth it, what goes is `apps-script/Phase0.gs`,
`apps-script/Phase0Dialog.html`, the Phase 0 branch in `Code.gs`'s `onOpen`, and
the gate's own controls in `preview.mjs` — the eight checks, `Run every gate
check`, and `Audit and compare with native`, all of which the page already hides
from an author.

That last removal is also the moment to fold `Phase0Dialog.html` into
`WorkbookBuilderDialog.html`. The two speak one message protocol on purpose but
implement the postMessage handshake twice, which is a duplication the gate is
currently paying for.

Nothing else here is removable. `workbook:browser-verify` is what proves the two
Typst versions still agree, and `workbook:browser-bundle` is what generates the
schema validators the export runs.
