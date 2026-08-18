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

### The page is the mark

The 2026-08 brand identity is a sheet of ruled notebook paper: cream ground, soft
rules alternating solid and dashed, a rust vertical margin rule, the numeral four
in butter. A reading workbook is the thing that logo is a picture of.

So the workbook does not decorate itself with the logo. It reproduces the paper,
and lets the parts that are already functional carry the brand:

- **A rust margin rule** runs the full height of every interior page at 30 mm.
  Question numbers hang in the gutter outside it; the text block begins clear of
  it. It is the reason an unfilled page bottom now reads as paper with room left
  on it rather than as a layout that ran out — the earlier draft had no vertical
  structure, so every short page looked like a mistake.
- **Solid rules mean "write here"; dashed rules mean "fill this in."** The mark
  alternates the two, and the workbook reuses that alternation as a signal rather
  than as texture. Response lines are solid; name, date, and "found on page(s)"
  fields are dashed.
- **Covers reproduce the paper in full** — cream ground, rules edge to edge, the
  rust rule, the logomark at full strength. Nobody writes an answer on a cover,
  so it is the one place the brand is allowed to be loud.

Interior pages stay on white. A full-bleed cream ground is expensive on a home
printer and greys down pencil, and students print these themselves.

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
already running. That produced pages carrying a green Analysis band under a lit
butter Comprehension tab, with a head naming the wrong section — indefensible
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

A4. Margins are 36 mm left, 26 mm right, 20 mm top, 18 mm bottom, giving a
148 mm text block. The margins are asymmetric because the page has a spine, not
because of binding: the left margin is wide enough to hold the rust rule at
30 mm and a 10 mm number gutter outside it. Nothing depends on whether a sheet is
left- or right-hand, because students print single-sided.

Body text is 11 pt — larger than a typical adult book, because younger students
handwrite in these. Ruled lines are 8.5 mm apart, which suits a teenage hand;
younger cohorts may want that raised. `line-gap` in `tokens.typ` is the single
number most likely to need changing after the first real print with real
students.

Question numbers hang in the gutter outside the rule rather than indenting the
text. They align down the page without taking measure from either the prompt or
the answer lines.

### Colour

| Token | Value | Role |
| --- | --- | --- |
| `ink` | `#17342f` | The brand's black; a deep forest green |
| `muted` | `#5f7069` | Secondary type and furniture |
| `paper` | `#f7f3ea` | The cream of the mark; covers and panels |
| `coral-deep` | `#b84431` | The margin rule |
| `ruled` | `#c6d0c8` | Handwriting guides; dark enough for a home laser |

Section colours are the brand's method palette in method order — butter, sage,
aqua, lilac, for Comprehension, Analysis, Writing, Vocabulary. The sections keep
their working names because that is what is actually on the page; the palette is
what ties them to READ · THINK · SPEAK · WRITE.

**These four are fills, never type.** Every one of them fails contrast as text on
white. Each has a `-deep` partner in `tokens.typ` for the rare place a section
has to be named in its own colour.

Colour is never the only carrier of meaning — verified by rendering pages to
grayscale and confirming the hierarchy still reads. Every section is also named
in words and numbered.

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
