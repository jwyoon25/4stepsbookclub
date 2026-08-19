# Phase 0: the browser-compiler gate

The workbook builder's accepted direction is to keep Google Sheets as the
authoring surface, compile the workbook with Typst **in the author's browser**,
preview the real PDF, and save approved PDFs to Drive through Apps Script.
[`../BUILDER-ARCHITECTURE-DECISION.md`](../BUILDER-ARCHITECTURE-DECISION.md)
records why, and makes one demand before any of it is built: prove the compiler
and the Drive round trip work in the real Google environment.

This directory is that proof, and nothing more. It is a spike: when the gate has
been run and recorded, it either becomes the foundation of Phase 1 or it is
deleted.

```text
builder/
├── browser/
│   ├── workbook-compiler.mjs  # which files make a compilable project, and how to load them
│   ├── preview.html           # the preview window
│   ├── preview.mjs            # environment probe, compile, display, Drive hand-off
│   └── preview.css
└── apps-script/
    ├── Phase0.gs              # the menu item, the launcher, and the Drive write
    └── Phase0Dialog.html      # the dialog the preview window answers to
```

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

1. Add `Phase0.gs` and `Phase0Dialog.html` as new files, keeping those exact
   names. `Phase0Dialog.html` is loaded by name.
2. Replace `Code.gs` with this repository's copy, which adds the menu item.
3. Optionally set a `PREVIEW_URL` script property. The default is
   `http://localhost:8787/preview.html`.

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

## Removing the spike

Delete this directory, the `browser-bundle` entries from `.gitignore`, the three
`workbook:browser-*` scripts, `lib/browser-bundle.mjs`,
`lib/browser-verification.mjs`, `lib/typst-compiler.mjs`,
`lib/render-parity.mjs`, `scripts/build-browser-bundle.mjs`,
`scripts/serve-browser-bundle.mjs`, `scripts/verify-browser-compiler.mjs`,
`tests/workbook-browser-compiler.test.mjs`, the `typst-wasm` dependency, and the
Phase 0 branch in `Code.gs`'s `onOpen`. Nothing else depends on any of it.
