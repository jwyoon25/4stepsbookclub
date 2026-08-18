# Workbook Content Schema

Version 1 of the workbook content model uses JSON Schema 2020-12. Tutors will
work through the eventual builder UI; these files are the stable boundary
between that UI and the Typst renderer.

The founder-approved content and workflow requirements live in
[`../CONTENT-WORKFLOW-DECISIONS.md`](../CONTENT-WORKFLOW-DECISIONS.md).

## Files

- [`workbook.schema.json`](workbook.schema.json) validates full-workbook metadata
  and its ordered list of lesson files.
- [`lesson.schema.json`](lesson.schema.json) validates one lesson and its four
  required sections.
- [`examples/example-book/`](examples/example-book/) is a complete, valid example
  package.

## Production package shape

Each workbook gets its own directory under `workbooks/content/`:

```text
content/
└── the-book-id/
    ├── workbook.json
    └── lessons/
        ├── lesson-01.json
        ├── lesson-02.json
        └── lesson-03.json
```

`workbook.json` is the entry point. Its `lessonFiles` array is the authoritative
lesson order. A builder generates the workbook `id` and filenames; tutors do not
type or manage them.

## Schema conventions

- `schemaVersion` is `1` in both record types. A breaking content-model change
  requires a new version and an explicit migration.
- Unknown properties are rejected. This catches misspelled fields instead of
  silently dropping content.
- Optional text is omitted rather than saved as an empty string or `null`.
- Text fields contain Unicode plain text. Paragraph breaks are allowed, but
  Typst markup and layout commands are not.
- Array order determines question, writing-prompt, and vocabulary numbering.
  Authors do not enter printed numbers or labels such as `L3-C2`.
- Every lesson contains all four section arrays, and every array has at least one
  item.
- Required answer guidance for Reading Comprehension and Critical Thinking &
  Analysis is stored with the lesson because teacher PDFs are a required output.
  Writing guidance may also be supplied. None of it is rendered in a student
  PDF.

JSON Schema's `default` keyword documents a value; validation does not insert it
into the source file. The builder and renderer must apply these defaults when a
field is absent:

| Content | Default |
| --- | --- |
| Series title | `4steps Book Club Workbook` |
| Reading Comprehension response | Short answer (3 lines) |
| Critical Thinking & Analysis response | Short paragraph (6 lines) |
| Paragraph Writing response | Full page |

## Response-space choices

Every question and writing prompt accepts the same optional `responseSpace`
object. Omitting it applies that section's default from the table above.

The simple presets need only a mode:

```json
{
  "mode": "short-answer"
}
```

The simple preset modes are `short-answer`, `short-paragraph`,
`extended-answer`, and `full-page`. Their renderer-owned meanings are:

| Mode | Current meaning | Status |
| --- | --- | --- |
| `short-answer` | 3 lines; approximately 1–2 sentences | Locked |
| `short-paragraph` | 6 lines | Locked |
| `extended-answer` | Provisionally 12 lines; approximately half a page | Revisit after final page design |
| `full-page` | Fill one response page with lines | Locked |

The semantic `extended-answer` value is stored instead of the derived line
count. Its page-space mapping can therefore change after final line spacing is
known without editing lesson content.

For an exact positive number of lines:

```json
{
  "mode": "custom-lines",
  "lines": 10
}
```

For two or more full response pages, `pages` is the total number of pages:

```json
{
  "mode": "multiple-pages",
  "pages": 2
}
```

This provides fast common choices without taking away the tutor's ability to
request any positive line count.

## Vocabulary excerpt context

`excerptContext` describes what is happening in the story around `bookExcerpt`
so the student can recall that moment in the chapter. It does not explain the
word's usual context, connotation, or usage. Those are not fields in version 1.

## System-owned content

The following do not appear as tutor-editable schema fields:

- Section names, order, standard descriptions, and colors
- Question numbers and Google Docs response labels
- The required full-workbook `How to use this workbook` page
- The standalone-lesson cover note
- Page numbering, typography, spacing, pagination, and continuation labels
- Student-versus-teacher presentation

The full-workbook instruction page is generated exactly once after the workbook
cover. It is not included in standalone lesson PDFs.

## Package-level validation

Run the package validator from the repository root:

```bash
npm run workbook:validate -- workbooks/content/the-book-id/workbook.json
```

With no path, the command validates the example package. The loader in
`workbooks/lib/content.mjs` validates individual files and also checks that:

- Every `lessonFiles` path exists inside the workbook directory.
- A lesson path or symlink cannot escape the workbook directory.
- Every lesson file validates against `lesson.schema.json`.
- Lesson numbers are unique.
- Manifest order is preserved as the complete-PDF order.

It returns normalized lesson data with omitted section defaults filled in.
Response presets remain semantic; mapping them to physical lines and pages stays
the renderer's responsibility.
