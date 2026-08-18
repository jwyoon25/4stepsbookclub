# 4steps Workbook System

The internal publishing system that generates 4steps Bookclub workbooks with
Typst.

The design system is implemented and proven by a specimen. The tutor-facing
requirements are locked in
[CONTENT-WORKFLOW-DECISIONS.md](CONTENT-WORKFLOW-DECISIONS.md), their JSON model
is defined in [schema/](schema/README.md), and the data-driven renderer turns a
validated content package into student and teacher PDFs. The staff editor is the
remaining layer.

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
npm run workbook:render          # render every example PDF variant
npm run workbook:build           # build the compilation smoke test
npm run workbook:watch
```

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

`workbook:specimen` writes `output/specimen.pdf`, a nine-page proof of the page
grammar with placeholder content. It is the file to look at when changing
anything in `system/`. Generated PDFs are ignored by Git.

## The design in one paragraph

The brand mark is a sheet of ruled notebook paper, and a reading workbook is the
thing that mark is a picture of — so the workbook reproduces the paper rather
than decorating itself with the logo. A rust margin rule runs down every interior
page with question numbers hanging outside it; solid rules mean "write here" and
dashed rules mean "fill this in"; four index tabs on the outer edge show which of
the four sections you are in. Covers reproduce the cream ruled ground in full.
Reasoning for all of it is in [DESIGN-DECISIONS.md](DESIGN-DECISIONS.md).

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
│   └── content.mjs       # package loading, validation, and default application
├── output/               # Generated files; PDFs are ignored by Git.
├── scripts/
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
