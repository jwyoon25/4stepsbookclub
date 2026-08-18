# Workbook Content and Workflow Decisions

- **Status:** Locked
- **Confirmed with the founder:** 2026-08-19

This is the authoritative specification for the information tutors provide, the
controls available to them, and the PDF outputs produced by the workbook
builder. Changes to these requirements need founder reconfirmation.

It does not choose the editor framework, authentication method, or build
infrastructure. Those remain implementation decisions. The JSON representation
chosen during implementation is documented in `schema/README.md`.

## Authoring boundary

Tutors author curriculum content and may adjust the amount of student response
space. The system owns all presentation decisions, including the layout
template, typography, font sizes, default line spacing, question numbering,
pagination, continuous full-workbook page numbering, and the visual distinction
between student and teacher versions.

Tutors never edit Typst or manually place page breaks.

## Full-workbook information

Required:

- Book title
- Author
- Workbook or series title, pre-filled with the standard 4steps title
- Lesson range, such as `Lessons 1–12`

Optional:

- Cover subtitle or description

Every full-workbook PDF contains exactly one required **How to use this
workbook** page. It appears after the workbook cover. Standalone lesson PDFs do
not contain this page.

## Lesson information

Required:

- Lesson number
- Lesson title
- Chapter or page range

Optional:

- Short lesson introduction or framing note
- General instructions for students

Every lesson always contains these four sections, in this order:

1. Reading Comprehension
2. Critical Thinking & Analysis
3. Paragraph Writing
4. Vocabulary

## Reading Comprehension

Each question contains:

- Question text — required
- Passage or quotation from the book — optional
- Student response space — Short answer (3 lines) by default
- Tutor note or answer guidance — required when a teacher version is requested

The tutor may replace the default with any response-space preset or any positive
number of lines.

## Critical Thinking & Analysis

Each question contains:

- Question text — required
- Passage or quotation from the book — optional
- Student response space — Short paragraph (6 lines) by default
- Tutor note or answer guidance — required when a teacher version is requested

The tutor may replace the default with any response-space preset or any positive
number of lines.

## Paragraph Writing

Each writing item contains:

- Writing prompt — required
- `Before you write` hints or steps — optional
- Response space — one page by default
- Example structure or rubric — optional

The tutor may replace the default with any response-space preset or any positive
number of lines. A lesson may contain more than one writing prompt.

## Response-space choices

Every Comprehension question, Analysis question, and Writing prompt uses the
same tutor-facing chooser:

- **Short answer** — 3 lines, intended for 1–2 sentences
- **Short paragraph** — 6 lines
- **Extended answer** — provisionally 12 lines and approximately half a page
- **Full page** — all available writing lines on one response page
- **Multiple pages** — the tutor chooses the number of full response pages
- **Custom lines** — the tutor enters any positive number of lines

The `Extended answer` mapping is not locked. Its current 12-line / half-page
description must be reviewed after the final page geometry and line spacing are
locked. Content records store the semantic choice `Extended answer`, not the
number 12, so changing that mapping will not require curriculum data edits.

## Vocabulary

Each entry contains:

- Vocabulary word — required
- Korean meaning — required
- English definition — required
- Excerpt from the book — required
- Excerpt context — required
- Chapter reference — optional

Part of speech is not part of the agreed entry format. Tutor-authored vocabulary
must never be rewritten, shortened, simplified, or reordered by the system.
`Excerpt context` explains what is happening in the story around the excerpt so
students can remember that moment in the chapter. It is not a definition, usage
note, or explanation of the vocabulary word itself.

## Builder workflow

The workbook builder must support:

- Pasting multiple questions or vocabulary rows from Google Sheets in one action
- Applying the response-space defaults automatically while allowing tutor
  overrides
- Showing a generated PDF preview before submission or final export

## Required outputs

The system produces:

- Standalone lesson PDFs
- A complete PDF containing all lessons
- Student versions
- Teacher or answer-key versions

Complete-workbook PDFs use continuous automatic page numbering across all
lessons. Teacher-only guidance is omitted from student versions.

## Implementation choices not settled here

The requirements above are locked. The following may be chosen during
implementation without changing this specification:

- Decap CMS or a purpose-built editor
- Authentication and permissions
- Draft, autosave, approval, and version-history mechanics
- Where and how Typst compilation runs
