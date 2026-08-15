# 4steps Workbook System

This directory is the initial home for the internal publishing/build tool that
will eventually generate 4steps Bookclub workbooks with Typst.

The current project is intentionally only infrastructure scaffolding. The
smoke test in `src/main.typ` verifies that the Typst source-to-PDF workflow can
be wired up; it is not a workbook design or a production template.

## Prerequisites

The local Typst CLI is the only additional dependency required for this
scaffold. Check whether it is available with:

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
npm run workbook:build
npm run workbook:watch
```

The build command writes the smoke-test PDF to
`workbooks/output/workbook-smoke-test.pdf`. Generated PDFs in that directory
are ignored by Git.

## Project shape

```text
workbooks/
├── README.md
├── assets/       # Future project-owned publishing assets.
├── content/      # Future book- and lesson-specific curriculum data.
├── output/       # Generated files; PDFs are ignored by Git.
├── src/
│   └── main.typ  # Minimal Typst compilation smoke test.
└── system/       # Future deterministic workbook presentation logic.
```

The content representation is intentionally undecided. The `content/`,
`system/`, and `assets/` boundaries leave room to introduce that separation
later without committing to a schema or visual design prematurely.

## Typst.app compatibility

The core Typst source should remain portable between the local CLI and a future
Typst.app project. Keep project resources relative to this project, avoid
developer-machine-specific absolute paths, and keep future fonts/assets with
the project where licensing permits. A later staff-facing Typst.app workflow
can copy or deploy the stable project without making Typst.app part of local
development.
