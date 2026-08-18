# Workbook Design Decisions

A running log of settled design decisions and deliberately deferred questions for
the workbook publishing system. The design is implemented in `system/` and proven
in `src/specimen.typ`; there is still no content schema.

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

### Where "how to use this workbook" lives

Because there is no reliable back-of-cover page, the standing reference material
(response modes, Google Docs labelling convention, what each section asks for)
is handled in two places:

- **Full-book builds:** a single "How to use this workbook" page following the
  workbook cover.
- **Standalone lesson builds:** compressed to the one-line labelling note on the
  lesson cover. A single lesson does not get a full instruction page.

### Vocabulary is reference-only

Vocabulary entries present tutor-authored content for reading, not for practice.
No response space is allocated per entry.

Consequence: the vocabulary section stays roughly half the length it would be
with practice lines, and vocabulary pages contain no writing surface at all —
which means branding treatment there can be slightly more present than on
question pages.

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
lesson number, title, chapter range, framing note, section list, and the
name/date field. Content pages then begin directly with the first section band.

### Writing surface: a page of its own, filled to the footer

A writing prompt takes a page of its own, and its ruled surface fills that page
down to the footer.

This is a revision of the original plan, which allowed the surface to flow
across a page break with a label on each side. Building it showed why that does
not work: the author cannot know where the break will land, so the label ends up
in the wrong place and the surface splits silently — reproducing the reference
PDF's worst habit, writing space separated from the prompt explaining it.

It is implemented without any explicit page break. The prompt, its scaffold, and
a minimum surface form one unbreakable block, tall enough that it cannot sit low
on a page; when it does not fit, the engine moves the whole thing forward and
carries the sticky section band with it. The surface is then topped up to the
footer. An explicit break would have stranded the section band on the page it
left behind — the exact orphan this design exists to prevent.

Longer responses get an additional, deliberate continuation page, labelled in
the running head and with the prompt echoed at the top.

### Grayscale legibility is load-bearing

The workbook must be fully usable printed black-and-white. All hierarchy works
through type size, weight, and spacing. Color, if used at all, carries only
secondary meaning and never the primary signal.

### Branding never competes with handwriting

Full brand expression on covers; a quiet mark in page furniture on interior
pages; a watermark behind interior pages at 6% alpha.

The watermark does sit behind writing surfaces — this is a revision of an earlier
"no watermark behind writing" rule, which produced pages with no visible
ownership at all. The rule that actually matters is about *strength*, not
position: at 6% the mark is far lighter than any pencil or pen, and lighter than
the ruled guide lines themselves. What the reference workbook got wrong was
repeated dark diagonal text, not the existence of a watermark.

### Typefaces

All three are SIL Open Font License, vendored in `assets/fonts`, and embedded in
the PDF by Typst. Vendoring rather than relying on system fonts is what makes a
build reproducible on any machine and legally distributable.

| Role | Face | Why |
| --- | --- | --- |
| Reading matter — prompts, quotes, definitions | Source Serif 4 | Academic without being fusty; sturdy at small sizes, so it survives a home laser printer where a finer face like Garamond would break up |
| Page furniture — labels, running heads, section names | Source Sans 3 | Same designer and skeleton as the serif, so structure and content never compete |
| Large cover titles | Source Serif 4 Display | A genuine optical size, not the text face scaled up |
| Korean glosses | Pretendard Std | Very legible at gloss size; a sans gloss also reads as annotation rather than as prose. Myeongjo-style serifs have hairlines that home printers drop |

This mirrors the website's existing serif + sans pairing rather than inventing a
separate identity.

### Page metrics

A4. Symmetric 25 mm side margins, 22 mm top, 20 mm bottom. Text block 160 mm,
split into a 13 mm rail and a 142 mm content column with a 5 mm gutter.

Body text is 11 pt — larger than a typical adult book, because younger students
handwrite in these. Ruled lines are 9 mm apart, which suits a teenage hand;
younger cohorts may want that raised.

The rail holds question labels and section letters and is otherwise deliberately
empty: it gives handwriting students somewhere to make margin notes and
GoodNotes users somewhere to drop annotations without covering the prompt.

### Colour

Slate blue, warm cream, and a terracotta accent, taken from the website palette.
Colour is never the only carrier of meaning — verified by rendering pages to
grayscale and confirming the hierarchy still reads.

## Deferred — revisit before implementation locks

### Tutor-declared writing space per prompt

**Currently:** writing response space is a fixed default size for all extended
writing prompts.

**To explore:** letting tutors declare a response size per prompt (e.g.
short / medium / extended / full-page) so a two-sentence reflection and a full
analytical paragraph don't get identical space.

**Why it's deferred:** worth discussing with tutors first. Fixed sizing is more
consistent and easier to keep visually disciplined; per-prompt sizing is more
efficient with paper and better matched to the actual task, but pushes a layout
decision onto whoever authors content, and inconsistent authoring would show up
directly as an inconsistent-looking workbook.

**When revisiting:** if adopted, the sizes should stay a small fixed set of named
options rather than free-form measurements, so the vertical rhythm survives.

### Bound-print build options

Mirrored margins and recto-start for lesson covers would both be correct if 4steps
ever produces a professionally printed and bound workbook. Both are deliberately
not built now — see "No page-parity dependence". Revisit only if a print run
becomes real.

### Teacher guide / answer key

Not currently required. If added, subjective questions would likely carry
evidence targets, acceptable interpretations, or grading guidance rather than
fixed answers. The "before you write" scaffold block on writing prompts is the
natural structural home for this.

### Content schema

Deliberately undecided until the visual design and page grammar are settled.
