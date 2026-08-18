# Workbook Design Decisions

A running log of settled design decisions and deliberately deferred questions for
the workbook publishing system. The design is implemented in `system/` and proven
in `src/specimen.typ`. The authoring requirements are locked in
`CONTENT-WORKFLOW-DECISIONS.md`, and their JSON representation is defined in
`schema/`. The data-driven renderer is implemented; the staff editor remains.

The purpose of this file is to keep decisions and their reasoning attached to the
project rather than living only in conversation. Add to it as decisions are made
or revisited.

## Settled

### Distribution model (drives several decisions below)

Classes are online. Workbooks are delivered to students as PDFs. Students choose
how to use them:

- Younger students are required to print and handwrite.
- Older students may annotate digitally (GoodNotes) or type responses in Google
  Docs.

There is no professional print run and no binding. The student's own printer is
the output device, and printing cost is borne by the student or their family.

Consequences:

- Page count matters more than it would for a bound book, because someone pays
  per page at home. It still ranks last in the pagination priority order, but
  gratuitous pages are a real cost, not an abstract one.
- The design must never depend on which side of a sheet a page lands on
  (see "No page-parity dependence").
- The PDF is also read on screen, so nothing may rely on facing-page spreads.

### No page-parity dependence

The layout never assumes a page is left-hand or right-hand, and never inserts
blank pages to control where a page falls.

- **Margins are symmetric**, not mirrored. Mirrored margins are correct for bound
  books but wrong here: they visibly alternate when the PDF is read on screen or
  printed single-sided, which is the common case.
- **No recto-start** for lesson covers. Forcing a right-hand start requires
  inserting blank pages, which a student printing at home would pay to print.
- Nothing is designed for "the back of a page" — including the back of a lesson
  cover — because in single-sided printing that surface does not exist.

If a bound print run is ever produced, mirrored margins and recto-start would be
worth revisiting as build options. Not worth building speculatively now.

### Question labels for Google Docs responses

Format: `L3-C2` — lesson number, section letter, question number within the
section. Section letters: `C` comprehension, `A` analysis, `W` writing. Hyphen
rather than a middot or other typographic separator, because students type these
by hand into a Doc.

**Printed form:** questions are numbered plainly (`1)`, `2)`) and restart in each
section. The lesson number is in the footer and the step is in the running head,
so the full label is always reconstructable. The lesson cover carries a note
explaining the convention.

This keeps the page quiet while staying unambiguous across a whole book. Printing
`L3-C2` beside every question would be more foolproof but noisier, and was
rejected on those grounds.

### Page references belong inside the response

When students quote or refer to evidence, they put the relevant page number in
parentheses within their answer, for example `(p. 47)`. Questions do not carry a
separate "Found on page(s)" field. Keeping the citation beside the sentence or
quotation makes the connection clearer and removes redundant form furniture.

### Guidance and requirements are part of the question

Every Comprehension question, Analysis question, and Writing prompt may carry an
optional tutor-authored guidance list. It can specify response length, paragraph
structure, required quotations, evidence, or another useful constraint. The
list appears in a `Guidance & requirements` panel directly beneath the prompt in
both student and teacher editions because it tells the student how to answer; it
is not answer-key content.

Writing previously had a separate `Before you write` hints list. That concept is
now folded into the common guidance list so tutors learn one control and the
renderer has one student-facing treatment. Teacher-only expected answers and
rubrics remain in visually separate panels.

### Where "how to use this workbook" lives

Because there is no reliable back-of-cover page, the standing reference material
(response modes, Google Docs labelling convention, what each section asks for)
is handled in two places:

- **Full-book builds:** a single "How to use this workbook" page following the
  workbook cover, with no repeated copies inside individual lessons.
- **Standalone lesson builds:** one full instruction page following the lesson
  cover, so the handout remains self-contained when distributed separately.

### Vocabulary is reference-only

Vocabulary entries present tutor-authored content for reading, not for practice.
No response space is allocated per entry.

Consequence: the vocabulary section stays roughly half the length it would be
with practice lines, and vocabulary pages contain no writing surface at all —
which means branding treatment there can be slightly more present than on
question pages.

### Vocabulary context describes the excerpt, not the word

Each vocabulary entry includes an excerpt from the book and an excerpt-context
note. That note reminds the student what is happening in the story around the
quoted moment. It is not a lexical usage note, a second definition, or an
explanation of how the vocabulary word is normally used.

### Vocabulary is set as entry blocks, not a table

Each entry is a stacked block with hanging field labels, not a row in a
five-column grid. Blocks give every field the full text measure, grow
independently when tutor content is long, and paginate cleanly between entries.

This is the direct fix for the reference PDF's densest failure, where five fields
forced into A4-width columns produced definitions wrapping at a few words per
line and rows splitting across page breaks.

### Tutor-authored vocabulary content is never altered

The system may wrap, paginate, and label it. It must not rewrite, shorten,
reorder, or simplify it.

### Two cover levels

- **Workbook cover** — one per compiled workbook, at the front.
- **Lesson cover** — one per lesson, a full page.

The lesson cover absorbs what would otherwise be a separate lesson opener block:
lesson number, title, chapter range, framing note, and section list. Content
pages then begin directly with the first section band.

### Writing surface defaults to one page

A writing prompt gets one page of response space by default. Tutors may override
the line count and request deliberate continuation pages. The layout engine,
rather than the tutor, remains responsible for placing the prompt and its
response surface safely on the page.

This is a revision of the original plan, which allowed the surface to flow
across a page break with a label on each side. Building it showed why that does
not work: the author cannot know where the break will land, so the label ends up
in the wrong place and the surface splits silently — reproducing the reference
PDF's worst habit, writing space separated from the prompt explaining it.

It is implemented without any author-supplied page break. The prompt, its
scaffold, and its response surface form one unbreakable block; when it does not
fit, the engine moves the whole thing forward and carries the sticky section
band with it. For the default one-page response, the surface is topped up to the
footer. An explicit break would have stranded the section band on the page it
left behind — the exact orphan this design exists to prevent.

Longer responses get an additional, deliberate continuation page, labelled in
the running head and with the prompt echoed at the top.

### Tutors choose response space semantically or by exact line count

Every question and writing prompt offers the same response-space choices: Short
answer, Short paragraph, Extended answer, Full page, Multiple pages, or a custom
positive number of lines. Section defaults make the common choice effortless,
but tutors may override them per item.

Short answer maps to 3 lines and Short paragraph to 6. Extended answer is
provisionally 12 lines and described as approximately half a page. That mapping
is deliberately not locked: it must be reviewed after the final line spacing and
page geometry are settled. Content stores the semantic choice rather than the
derived number, so revising the mapping will not require curriculum edits.

### Grayscale legibility is load-bearing

The workbook must be fully usable printed black-and-white. All hierarchy works
through type size, weight, and spacing. Color, if used at all, carries only
secondary meaning and never the primary signal.

### Editorial page system and four-step cover rail

The workbook uses the visual system ported from the approved workbook design:
white paper, a rust editorial rule, restrained serif typography, and a fixed
green–coral–teal–purple sequence for Read, Think, Speak, and Write.

- **Workbook covers** carry a 24 mm full-height rail split into four equal colour
  bands. Each band names its step and section vertically. The wide brand logotype,
  a thin rust rule, large book title, author, lesson range, and website mark form
  the remaining hierarchy.
- **Lesson covers** use the same four colour bands without vertical labels. They
  show the lesson identity, chapter range, framing copy, optional instructions,
  derived section item counts, and Google Docs/teacher note.
- **Interior pages** keep a rust rule at 24 mm and begin content at 29 mm. Plain
  question numbers hang outside the rule. Four tabs at the outer edge repeat the
  method colours, with the current step wider and more saturated.
- **Solid rules mean "write here."** Page references are not a separate field
  and remain parenthetical citations within the student's response.

All pages stay white. This preserves the approved visual composition, reduces
home-printer ink coverage, and keeps pencil and annotation contrast high.

### The centred watermark is withdrawn

Interior pages carry no watermark. This reverses the previous decision, which
put the logomark behind every page at 6% alpha.

That decision was a correction to an earlier draft that had no visible ownership
at all, and it fixed the right problem the wrong way. With a rust spine, section
tabs, a running head, and a wordmark in every footer, the page is now branded
several times over, and a pale disc floating behind the ruled lines read as a
smudge on the writing surface — the exact defect logged against the reference
workbook. Ownership is carried by furniture that also does a job.

### Section tabs are the finder and the progress indicator

Four index tabs run down the outer edge of every interior page, the current
section saturated and extended, the others tinted. They are lifted from the
site's own `.step-tabs`, where the same four colours already stand for the same
four steps.

They are a section finder when flipping and a progress indicator when reading,
and they cost nothing to print. They do not bleed off the edge: a home printer
cannot print to the edge, and a tab clipped by an unprintable margin looks broken
rather than deliberate.

### A section takes the page it begins on

If a section band appears in the top half of a page, that page's running head and
tab belong to the new section, even when the page opens with the tail of the
previous one.

This reverses the earlier rule, which gave the page to whichever section was
already running. That produced pages carrying an Analysis band under a lit
Comprehension tab, with a head naming the wrong section — indefensible
once the tabs existed, because the tabs are a finder and someone flipping for
Analysis has to land on the page the Analysis band is on.

The half-page test is the guard: a band starting near the foot of a page has not
really taken it, so the running section keeps it.

### A section that ends short hands the page back

A section almost never ends level with the foot of a page, and a section whose
last question is followed by a writing prompt leaves most of a sheet behind —
a writing surface is an unbreakable block, so it moves whole to a page it fits
on. Those were the emptiest pages in the book.

`ruled-tail` fills the remainder with a labelled ruled area. Every use is a real
invitation rather than filler: "Anything you noticed that the questions didn't
ask about" after Analysis, "Words you met in these chapters" after Vocabulary.
Close reading is the point of the book, and a student noticing something
unprompted is the behaviour worth making room for.

It renders only when enough of the page is left to be worth using, so an author
can call it at the end of any section without ever producing a stub.

### Typefaces

Both faces are SIL Open Font License, both are Korean-capable, and both are
vendored in `assets/fonts` and embedded in the PDF by Typst. Vendoring rather
than relying on system fonts is what makes a build reproducible on any machine
and legally distributable.

| Role | Face | Why |
| --- | --- | --- |
| Reading matter, cover and section titles, Korean glosses | Gowun Batang | The logotype's own face, so the workbook and the mark are set in the same voice. Covers Latin and Hangul in one family, which is what retires the separate Korean gloss face |
| Page furniture — labels, running heads, instructions, scaffolds | IBM Plex Sans KR | The website's sans, also Korean-capable; a clear sans against the serif keeps structure and content from competing |

Both are the website's own `--font-display` and `--font-sans`, so the workbook
and the site cannot drift apart.

Gowun Batang ships exactly two weights, regular and bold. Nothing may ask for
another: Typst would synthesise it, and a synthesised semibold does not match the
logo.

This replaces Source Serif 4 / Source Sans 3 / Pretendard Std, which belonged to
the previous brand. It also closes a real defect: the old stack named a Korean
face that was never actually vendored, so every Korean gloss silently fell back
to whatever the build machine happened to have.

### Page metrics

A4. Margins are 29 mm left, 24 mm right, 20 mm top, 18 mm bottom, giving a
157 mm text block. The margins are asymmetric because the page has a spine, not
because of binding: the rust rule sits at 24 mm and the 8 mm question-number
gutter hangs outside it. Nothing depends on whether a sheet is left- or
right-hand, because students print single-sided.

Body text is 11 pt — larger than a typical adult book, because younger students
handwrite in these. Ruled lines are 8.5 mm apart, which suits a teenage hand;
younger cohorts may want that raised. `line-gap` in `tokens.typ` is the single
number most likely to need changing after the first real print with real
students.

The running head sits at 14 mm from the top edge and the footer at 14 mm from
the bottom edge, matching the approved HTML composition. Handwriting rules are
0.2 mm; the rust spine and quiet panel borders are 0.25 mm. The
section opener follows the reference's fixed vertical stack so its step label,
title, description, and first question do not drift as copy elsewhere changes.

Vocabulary deliberately keeps the reference's roomier line-box rhythm: 2.4 mm
before each field and 4.5 mm between entries, with enough breathing room around
single-line fields to match the HTML layout. Pagination still happens between
whole entries and remains content-dependent.

Question numbers hang in the gutter outside the rule rather than indenting the
text. They align down the page without taking measure from either the prompt or
the answer lines.

### Colour

| Token | Value | Role |
| --- | --- | --- |
| `ink` | `#17342f` | The brand's black; a deep forest green |
| `muted` | `#5f7069` | Secondary type and furniture |
| `paper` | `#f7f3ea` | Warm neutral for restrained callout panels |
| `coral-deep` | `#b84431` | The margin rule |
| `ruled` | `#c6d0c8` | Handwriting guides; dark enough for a home laser |

Section colours follow the approved design in method order: green `#a9cdb0`,
coral `#f0b6a4`, teal `#96cdc9`, and purple `#bfb2dc`, for Reading
Comprehension, Critical Thinking & Analysis, Paragraph Writing, and Vocabulary.
The palette ties them to READ · THINK · SPEAK · WRITE.

**These four are fills, never type.** Every one of them fails contrast as text on
white. Each has a `-deep` partner in `tokens.typ` for the rare place a section
has to be named in its own colour.

Colour is never the only carrier of meaning — verified by rendering pages to
grayscale and confirming the hierarchy still reads. Every section is also named
in words and numbered.

## Deferred — revisit only when the use case becomes real

### Bound-print build options

Mirrored margins and recto-start for lesson covers would both be correct if 4steps
ever produces a professionally printed and bound workbook. Both are deliberately
not built now — see "No page-parity dependence". Revisit only if a print run
becomes real.
