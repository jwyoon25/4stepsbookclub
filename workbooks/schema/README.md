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
- Answer guidance for Reading Comprehension and Critical Thinking & Analysis is
  stored with the lesson whenever teacher PDFs are requested. Student-only
  exports may omit it; the renderer rejects a teacher export that does not
  provide it. Writing guidance may also be supplied. None of it is rendered in
  a student PDF.
- Optional `responseGuidance` may be attached to any Comprehension question,
  Analysis question, or Writing prompt. It is a list of student-facing
  directions or requirements and is rendered unchanged in both editions.

### Layout-safety limits

The schema places generous maximum lengths on cover copy, prompts, quotations,
guidance items, teacher notes, rubrics, and vocabulary fields. A guidance list
contains at most six concise requirements. These limits are part of the editor
contract: they let the staff UI warn a tutor before content reaches PDF export.

The package loader also checks combinations that can overflow even when every
individual field is valid—for example, a long prompt plus six long guidance
items beside a 14-line response area. Korean and Han characters count as wider
layout units in this check. An individual unbroken segment is limited to 80
characters so pasted URLs or malformed text cannot run beyond the page edge. The
system never truncates or rewrites tutor content; it rejects unsafe content with
the exact lesson and item path so the tutor can revise it deliberately.

JSON Schema's `default` keyword documents a value; validation does not insert it
into the source file. The builder and renderer must apply these defaults when a
field is absent:

| Content | Default |
| --- | --- |
| Series title | `4steps Book Club Workbook`; the editor pre-fills it and the loader restores it when omitted |
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
| `full-page` | Fill one response page with 7 mm lines | Locked |

The semantic `extended-answer` value is stored instead of the derived line
count. Its page-space mapping can therefore change after the final page design
is approved without editing lesson content.

Full-page modes derive their rendered line count from the remaining height down
to the standard bottom boundary. Exact finite line counts remain atomic; when a
prompt, guidance, and all requested lines cannot fit together, the whole item
moves to the next page. Exact responses longer than the 14-line prompt-page cap
continue on explicitly labelled pages that hold up to 35 lines at the standard
7 mm rhythm.

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

## Guidance fields

`responseGuidance` is the single student-facing guidance field for every kind of
written response. Each array item becomes one bullet in a `Guidance &
requirements` panel. Using one consistent field avoids a separate Writing-only
`hints` concept in the builder.

For compatibility with early version 1 content, the package loader still
accepts a deprecated Writing `hints` array and migrates its items into
`responseGuidance`. New content and the staff editor must only write
`responseGuidance`; normalized build data never contains `hints`.

```json
{
  "prompt": "Was the narrator's choice justified?",
  "responseGuidance": [
    "Write two paragraphs.",
    "Use at least three short quotations from the book.",
    "Explain how each quotation supports your position."
  ],
  "teacherGuidance": "Accept either position when the evidence is relevant and explained."
}
```

The similarly named fields have different audiences:

| Field | Purpose | Student PDF | Teacher PDF |
| --- | --- | --- | --- |
| `responseGuidance` | Optional length, structure, quotation, or evidence requirements | Shown | Shown |
| `teacherGuidance` | Expected answer or teaching note | Hidden | Shown |
| `exampleStructureOrRubric` | Optional Writing assessment support | Hidden | Shown |

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
cover and is not repeated before its lessons. A standalone lesson PDF generates
its own copy directly after the lesson cover.

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
- Cover, question, guidance, and vocabulary combinations fit the standardized
  page geometry.

It returns normalized lesson data with omitted section defaults filled in.
Response presets remain semantic; mapping them to physical lines and pages stays
the renderer's responsibility.

## PDF rendering

After validation, render every required output from the same manifest:

```bash
npm run workbook:render -- workbooks/content/the-book-id/workbook.json
```

The build planner creates complete-workbook and standalone-lesson PDFs for both
student and teacher editions. It writes a temporary normalized JSON bundle for
each build, passes it to the generic Typst entry point, and removes the bundle
after compilation. A staged PDF is promoted to its final filename only when
Typst reports no warnings and the PDF audit confirms A4 geometry, correct
footers, in-bounds text, instruction-page count, section order, running-header
agreement, and edition separation. Tutors never author Typst or pagination
data.
