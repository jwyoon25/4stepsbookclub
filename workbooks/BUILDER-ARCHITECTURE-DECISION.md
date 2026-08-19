# Workbook Builder Architecture Decision

- **Status:** Accepted direction; browser compatibility gate pending
- **Decision date:** 2026-08-19
- **Scope:** Staff authoring, preview, PDF generation, and Drive delivery

This record captures the agreed direction for the first workbook-builder MVP.
It complements the founder-confirmed requirements in
[`CONTENT-WORKFLOW-DECISIONS.md`](CONTENT-WORKFLOW-DECISIONS.md); it does not
change those requirements or the schema-v1 content model.

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

## Next authorized implementation step

Build only the Phase 0 compatibility spike. If it passes, record the measured
browser, compilation, preview, Drive-transfer, and audit results in this file,
change the status to **Accepted and validated**, and proceed to Phase 1.
