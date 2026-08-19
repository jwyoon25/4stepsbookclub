# 4steps Workbook System

The internal publishing system that generates 4steps Bookclub workbooks with
Typst.

The design system is implemented and proven by a specimen. The tutor-facing
requirements are locked in
[CONTENT-WORKFLOW-DECISIONS.md](CONTENT-WORKFLOW-DECISIONS.md), their JSON model
is defined in [schema/](schema/README.md), and the data-driven renderer turns a
validated content package into student and teacher PDFs. The first staff-facing
authoring MVP is a Google Sheets-ready template with a checked `.xlsx` importer.

## Prerequisites

The local Typst CLI is the only additional dependency. Check whether it is
available with:

```bash
typst --version
```

On macOS, install it with Homebrew if needed:

```bash
brew install typst
```

No Typst account or Typst.app subscription is required for local development.

## Commands

From the repository root:

```bash
npm run workbook:specimen        # build the design specimen
npm run workbook:specimen:watch  # rebuild it on every save
npm run workbook:validate        # validate the example content package
npm run workbook:import-sheet -- path/to/downloaded-workbook.xlsx
npm run workbook:render          # render every example PDF variant
npm run workbook:build           # build the compilation smoke test
npm run workbook:watch
```

## Google Sheets authoring MVP

Use the checked template at
`outputs/2026-08-19-google-sheets-mvp/4steps-workbook-authoring-template.xlsx`:

1. Upload the `.xlsx` file to Google Drive, open it with Google Sheets, and make
   a copy for the book.
2. Edit the workbook and lesson tabs. Add one question, prompt, or vocabulary
   entry per row. Do not rename tabs or column headings.
3. In Google Sheets, choose **File → Download → Microsoft Excel (.xlsx)**.
4. Import the download from the repository root:

   ```bash
   npm run workbook:import-sheet -- path/to/downloaded-workbook.xlsx
   ```

The command creates a validated schema-v1 package under
`workbooks/content/<generated-book-id>/`. It stops with a tab, row, and field
message when the spreadsheet contract is invalid. The generated ID is based on
the book title; use `--id existing-book-id` to assign a stable ID explicitly.

To import into a chosen directory and retain its existing manifest ID:

```bash
npm run workbook:import-sheet -- path/to/downloaded-workbook.xlsx \
  --output-dir workbooks/content/existing-book-id
```

To import, validate, and immediately create all student and teacher PDFs:

```bash
npm run workbook:import-sheet -- path/to/downloaded-workbook.xlsx --render
```

This MVP intentionally keeps Google Sheets as the editor and the repository as
the controlled generation boundary. PDF preview is therefore a download-and-run
step, not a live viewer inside the sheet. A split editor/PDF viewer can be added
after the authoring contract is proven with real workbook makers.

Validate a production manifest by passing its path after `--`:

```bash
npm run workbook:validate -- workbooks/content/the-book-id/workbook.json
```

Render that package with the same manifest entry point:

```bash
npm run workbook:render -- workbooks/content/the-book-id/workbook.json
```

By default, output is written to `workbooks/output/`. To choose another output
directory:

```bash
npm run workbook:render -- workbooks/content/the-book-id/workbook.json \
  --output-dir path/to/output
```

For a package with the ID `the-book-id`, the renderer creates:

- `the-book-id-workbook-student.pdf`
- `the-book-id-workbook-teacher.pdf`
- `the-book-id-lesson-01-student.pdf` and one equivalent file per lesson
- `the-book-id-lesson-01-teacher.pdf` and one equivalent file per lesson

Complete-workbook PDFs contain the workbook cover, exactly one required
`How to use this workbook` page, and every lesson in manifest order; the page is
not repeated inside those lessons. Standalone lesson PDFs contain their own copy
directly after the lesson cover. Student editions contain response lines;
teacher editions replace those surfaces with the stored teacher guidance and
optional writing rubric. Optional tutor-authored `Guidance & requirements`
lists stay attached to their questions in both editions because they are
directions for the student, not answer-key content.

Every render is staged under a temporary filename and replaces the previous PDF
only after passing the consistency audit. A successful export requires zero
Typst warnings, A4 page geometry, in-bounds text, correct physical and printed
page totals, exactly one instruction page, the four sections in locked order,
matching section bands and running heads, and no teacher-only guidance in a
student PDF. `npm test` renders both the canonical package and a pagination
stress package so these checks run against actual PDFs rather than JSON alone.

`workbook:specimen` writes `output/specimen.pdf`, a nine-page proof of the page
grammar with placeholder content. It is the file to look at when changing
anything in `system/`. Generated PDFs are ignored by Git.

## The design in one paragraph

The workbook uses a clean editorial system on white A4 pages. Workbook and
lesson covers share a full-height green–coral–teal–purple method rail; interior
pages use a rust spine with question numbers hanging outside it and four index
tabs showing the active step. Solid rules mean "write here" and dashed rules
mean "fill this in." The wide logo lockup, serif titles, quiet sans-serif
furniture, and warm callout panels complete the ported design. Reasoning for all
of it is in [DESIGN-DECISIONS.md](DESIGN-DECISIONS.md).

## Project shape

```text
workbooks/
├── README.md
├── DESIGN-DECISIONS.md   # settled decisions and deferred questions, with reasoning
├── CONTENT-WORKFLOW-DECISIONS.md # locked authoring fields, defaults, and outputs
├── schema/               # versioned JSON Schemas, documentation, and examples
├── assets/
│   ├── fonts/            # Gowun Batang + IBM Plex Sans KR, vendored (OFL)
│   └── logo/             # logomark and logotype, derived from the website assets
├── content/              # Production book- and lesson-specific curriculum data
├── lib/
│   ├── build.mjs         # output planning and Typst build orchestration
│   ├── content.mjs       # package loading, validation, and default application
│   ├── pdf-audit.mjs     # post-render PDF consistency checks
│   └── sheet-import.mjs  # Google Sheets .xlsx contract and schema-v1 conversion
├── output/               # Generated files; PDFs are ignored by Git.
├── scripts/
│   ├── import-sheet.mjs     # command-line spreadsheet importer
│   ├── render-content.mjs   # command-line PDF renderer
│   └── validate-content.mjs # command-line content validator
├── src/
│   ├── main.typ          # Minimal Typst compilation smoke test.
│   ├── render.typ        # Generic JSON bundle entry point.
│   └── specimen.typ      # The design specimen.
└── system/
    ├── tokens.typ        # Every measurement, colour, and type size.
    ├── components.typ    # The page grammar.
    └── renderer.typ      # Content-to-component mapping and edition behavior.
```

Components must not hard-code values. Change a workbook's feel by editing
`tokens.typ`, not `components.typ`.

The authoring requirements, JSON representation, package loader, and Typst
renderer are connected. The future editor only needs to create schema-valid
content packages and invoke this existing build path. The `content/`, `system/`,
and `assets/` boundaries keep curriculum data independent from a particular
authoring tool.

## Fonts

Both faces are SIL Open Font License and are vendored rather than assumed to be
installed, so builds are reproducible on any machine and the PDFs are legally
distributable. They are the same two the website uses, so the workbook and the
site cannot drift apart.

Every build passes `--font-path workbooks/assets/fonts`; the npm scripts already
do. Compiling without it silently substitutes whatever the machine has.

## Logos

`assets/logo/` holds the full brand set, copied from
`website/public/images/logo/png/`: `logomark-large`, `logomark-small`, and
`logotype`, each in a `-light` and a `-dark` form. They are addressed by the
names in `tokens.typ`, never by path.

They are PNG rather than SVG because the source SVGs set letter-spacing with CSS
custom properties, which Typst's renderer does not support — imported as SVG the
glyphs collapse on top of each other.

Typst cannot read outside `workbooks/`, so these are copies. Re-run this from the
repository root when the brand assets change:

```bash
python3 - <<'PY'
from PIL import Image
src, dst = 'website/public/images/logo/png/', 'workbooks/assets/logo/'
for name in ('logomark-large-light', 'logomark-large-dark',
             'logomark-small-light', 'logomark-small-dark',
             'logotype-light', 'logotype-dark'):
    im = Image.open(src + name + '.png').convert('RGBA')
    im.crop(im.getbbox()).save(dst + name + '.png')
PY
```

## Typst.app compatibility

The core Typst source should remain portable between the local CLI and a future
Typst.app project. Keep project resources relative to this project, avoid
developer-machine-specific absolute paths, and keep fonts and assets with the
project. A later staff-facing Typst.app workflow can copy or deploy the stable
project without making Typst.app part of local development.
