// ---------------------------------------------------------------------------
// Page grammar components.
//
// Each component owns one role. Content is passed in; nothing here knows
// anything about a particular book or lesson.
//
// Pagination rules are enforced structurally, not by hand:
//   - `block(breakable: false)` keeps a question with its response area.
//   - `block(sticky: true)` keeps a heading with the content beneath it.
// ---------------------------------------------------------------------------

#import "tokens.typ": *

// --- Document state ---------------------------------------------------------

#let doc-book = state("book", "")
#let doc-lesson = state("lesson", "")

// Which section a page belongs to cannot use `state`: a header is laid out at
// the top of its page, before any state update made by content on that same
// page. A section beginning on page 3 would therefore never reach page 3's
// header. Instead each section drops a positioned marker, and the furniture
// works out which one applies by comparing page numbers.
#let section-marker(name, step: 0, force: false, continued: false) = [#metadata((
  name: name, step: step, force: force, continued: continued,
))#label("wb-section")]

// A section takes over the page it begins on, provided it begins in the top half
// of the text block. The tabs are a finder: someone flipping for Analysis should
// land on the page where the Analysis band is and see the Analysis tab lit, not
// the previous section's. An earlier draft gave the page to whichever section
// was already running, which left pages carrying a green band under a butter tab
// and a head naming the wrong section.
//
// The half-page test is the guard on that: a band that starts near the foot of a
// page has not really taken it, so the running section keeps it.
#let takes-page = margin-top + body-height / 2

// Precedence: a forced marker (continuation heading) > the last section to begin
// in the top half of this page > the section still running when the page opened
// > any section beginning on this page at all.
//
// Returns `none` on covers, or `(name, step, continued)` on interior pages.
#let active-section() = {
  let p = here().position().page
  let markers = query(<wb-section>)
  let on-page = markers.filter(m => m.location().position().page == p)
  let forced = on-page.filter(m => m.value.force)
  let opening = on-page.filter(m => m.location().position().y <= takes-page)
  let earlier = markers.filter(m => m.location().position().page < p)
  let carried = if earlier.len() > 0 { earlier.last().value } else { none }

  let chosen = if forced.len() > 0 {
    forced.first().value
  } else if opening.len() > 0 {
    opening.last().value
  } else if carried != none and carried.name != none {
    carried
  } else if on-page.len() > 0 {
    on-page.first().value
  } else { none }

  if chosen == none or chosen.name == none { return none }

  // A section that opted in gets "(continued)" on every page after the one it
  // started on. This is how a vocabulary list announces itself across a break
  // without anyone having to know in advance where the break lands.
  let carried-on = carried != none and chosen == carried and chosen.continued
  (
    name: if carried-on { chosen.name + " (continued)" } else { chosen.name },
    step: chosen.step,
    continued: carried-on,
  )
}

// --- Layout helpers ---------------------------------------------------------

#let caps(body, size: size-label, weight: "semibold", fill: faint, tracking: tracking-caps) = text(
  font: sans, size: size, weight: weight, fill: fill, tracking: tracking, upper(body),
)

// A ruled writing surface. Solid rules, because in this design solid means
// "write on this" and dashed means "fill this in".
#let response-lines(n) = stack(
  spacing: 0pt,
  ..range(n).map(_ => box(
    width: 100%,
    height: line-gap,
    place(bottom + left, line(length: 100%, stroke: stroke-ruled)),
  )),
)

// A short dashed field to be filled in — a name, a date, a page number.
#let dashed-field(label, width: 100%, label-width: 17mm) = box(width: width, height: 8mm, {
  place(bottom + left, dy: -1.9mm, caps(label, fill: muted))
  place(bottom + left, dx: label-width, line(length: 100% - label-width, stroke: stroke-field))
})

#let name-date-fields(width: 86mm) = block(width: width, {
  dashed-field("Name")
  v(4mm)
  dashed-field("Date")
})

// --- Page furniture ---------------------------------------------------------
//
// The spine: the rust margin rule and the section tabs. Together they are what
// gives an interior page vertical structure, so a page that stops short reads
// as paper with room left on it rather than as a layout that ran out.

#let margin-rule() = place(
  top + left,
  dx: rule-x,
  dy: 14mm,
  line(angle: 90deg, length: page-height - 28mm, stroke: stroke-margin),
)

#let section-tabs(active) = {
  for i in range(4) {
    let on = i + 1 == active
    place(
      top + left,
      dx: tab-x,
      dy: tab-top + i * (tab-height + tab-gap),
      rect(
        width: if on { tab-width-active } else { tab-width },
        height: tab-height,
        fill: if on { step-fill.at(i) } else { step-fill.at(i).lighten(62%) },
        radius: (right: tab-radius),
        stroke: none,
      ),
    )
  }
}

#let page-spine() = context {
  let section = active-section()
  if section != none {
    margin-rule()
    section-tabs(section.step)
  }
}

// The wordmark, typeset rather than placed as an image. The logotype lockup is
// a capsule the size of a stamp; shrunk to footer height its inner rules and
// "BOOK CLUB" turn to mud. Rebuilding it from the brand's own two faces stays
// crisp at 8pt and prints on any machine. The image lockup is for covers.
#let wordmark(size: 8.5pt) = box({
  text(font: serif, size: size, weight: "bold", fill: ink, "4steps")
  h(1.4mm)
  text(font: sans, size: size * 0.74, weight: "semibold", fill: muted, tracking: 0.09em, "BOOK CLUB")
})

#let running-head() = context {
  let section = active-section()
  if section != none {
    // The head sits over the text block, so it starts clear of the margin rule
    // and ends level with the block — the tabs live outside it.
    grid(
      columns: (1fr, auto),
      column-gutter: 4mm,
      align: horizon,
      text(font: serif, size: size-furniture, fill: muted, doc-book.get()),
      caps(section.name, size: size-furniture, fill: ink-soft),
    )
  }
}

#let running-foot() = context {
  let section = active-section()
  if section == none { return }
  let total = counter(page).final().first()
  let current = counter(page).at(here()).first()
  grid(
    columns: (auto, 1fr, auto),
    column-gutter: 4mm,
    align: horizon,
    wordmark(),
    text(font: sans, size: size-furniture, fill: faint, doc-lesson.get()),
    text(font: sans, size: size-furniture, fill: faint)[Page #current of #total],
  )
}

// --- Document wrapper -------------------------------------------------------

#let workbook(book: "", lesson: "", body) = {
  set page(
    paper: paper-size,
    margin: (
      top: margin-top, bottom: margin-bottom,
      left: margin-left, right: margin-right,
    ),
    header: running-head(),
    header-ascent: head-ascent,
    footer: running-foot(),
    footer-descent: foot-descent,
    background: page-spine(),
  )
  set text(font: serif, size: size-body, fill: ink-body, lang: "en")
  // Ragged right: at this measure justification opens rivers, and prompts read
  // better with an even word space.
  set par(leading: leading-body, justify: false)

  doc-book.update(book)
  doc-lesson.update(lesson)
  body
}

// --- Covers -----------------------------------------------------------------
//
// Covers reproduce the mark literally: cream ground, ruled lines edge to edge,
// rust margin rule. This is the one place the brand is allowed to be loud,
// because nobody writes an answer on a cover.

#let cover-paper() = {
  place(top + left, dx: -margin-left, dy: -margin-top, rect(
    width: page-width, height: page-height, fill: paper, stroke: none,
  ))
  // Ruled lines run the full sheet, alternating solid and dashed the way the
  // mark does.
  let n = int((page-height - cover-rule-top) / cover-rule-gap)
  for i in range(n) {
    place(top + left, dx: -margin-left, dy: -margin-top + cover-rule-top + i * cover-rule-gap, line(
      length: page-width,
      stroke: if calc.rem(i, 2) == 0 {
        0.5pt + ruled
      } else {
        (paint: ruled.lighten(28%), thickness: 0.5pt, dash: "densely-dashed")
      },
    ))
  }
  place(top + left, dx: rule-x - margin-left, dy: -margin-top, line(
    angle: 90deg, length: page-height, stroke: 0.8pt + coral-deep,
  ))
}

#let workbook-cover(book: "", author: "", series: "", span: "") = {
  section-marker(none)
  cover-paper()
  v(14mm)
  box(width: 46mm, image(logomark, width: 100%))
  v(18mm)
  caps(series, size: size-cover-series, fill: coral-deep)
  v(6mm)
  text(font: serif, size: size-cover-title, weight: "bold", fill: ink, book)
  v(4mm)
  text(font: serif, size: 13pt, fill: muted, author)
  v(1fr)
  text(font: sans, size: 10pt, fill: ink-soft, span)
  v(8mm)
  name-date-fields()
  v(2mm)
  pagebreak()
}

// The lesson cover absorbs what would otherwise be a separate lesson opener: a
// single lesson is often handed out on its own, so it needs its own identity,
// name field, and orientation.
#let lesson-cover(
  lesson: "",
  title: "",
  chapters: "",
  framing: "",
  sections: (),
  note: none,
) = {
  section-marker(none)
  cover-paper()
  v(12mm)
  grid(
    columns: (1fr, auto),
    align: horizon,
    caps(lesson, size: 11pt, fill: coral-deep),
    box(width: 30mm, image(logomark, width: 100%)),
  )
  v(1fr)
  text(font: serif, size: size-lesson-title, weight: "bold", fill: ink, title)
  v(3mm)
  text(font: serif, size: 12pt, fill: muted, chapters)
  v(8mm)
  block(width: 128mm, text(font: serif, size: size-body, fill: ink-body, framing))

  // The four sections of this lesson, shown as the tabs they will appear as.
  if sections.len() > 0 {
    v(10mm)
    caps("In this lesson", fill: muted)
    v(4mm)
    block(width: 100%, stack(
      spacing: 3mm,
      ..sections.enumerate().map(((i, s)) => grid(
        columns: (tab-width-active, 1fr),
        column-gutter: 5mm,
        align: horizon,
        rect(
          width: tab-width-active, height: tab-height,
          fill: step-fill.at(i), radius: (right: tab-radius), stroke: none,
        ),
        {
          text(font: sans, size: 9.5pt, weight: "semibold", fill: ink, s)
          h(3mm)
          text(font: sans, size: size-furniture, fill: faint, "Step " + str(i + 1))
        },
      )),
    ))
  }

  v(1fr)
  if note != none {
    block(
      width: 100%,
      inset: (x: 4mm, y: 3.4mm),
      radius: 2pt,
      fill: canvas,
      stroke: 0.5pt + line-soft,
      text(font: sans, size: 8.5pt, fill: ink-soft, note),
    )
    v(7mm)
  }
  name-date-fields(width: 100%)
  v(2mm)
  pagebreak()
}

// --- Section band -----------------------------------------------------------
//
// `sticky: true` is the anti-orphan rule: a band can never end a page, it is
// carried to the next page along with whatever follows it.
//
// The band opens with a coloured bar that starts on the margin rule and runs the
// full measure. Beginning it at the rule rather than at the text block is what
// ties the section to the page's spine — a bar that floats free of the rule
// reads as a stray swatch, which is exactly how the previous draft's did.

#let section-band(step, name, description, continued-label: false) = {
  section-marker(name, step: step, continued: continued-label)
  let c = step-fill.at(step - 1)
  let overhang = margin-left - rule-x
  block(
    sticky: true,
    width: 100%,
    above: space-band-above,
    below: space-band-below,
    {
      place(top + left, dx: -overhang, rect(
        width: block-width + overhang, height: band-bar-height,
        fill: c, radius: (right: tab-radius), stroke: none,
      ))
      v(band-bar-height + 3.5mm)
      caps("Step " + str(step), size: size-furniture, fill: step-deep.at(step - 1))
      v(1.6mm)
      text(font: serif, size: size-section-title, weight: "bold", fill: ink, name)
      v(2.6mm)
      block(width: 100%, text(font: sans, size: 8.5pt, fill: muted, description))
    },
  )
}

// --- Question unit ----------------------------------------------------------
//
// Where in the book the answer came from. Carried over from the existing 4steps
// workbook, where every question has a "page(s):" field — it makes students
// evidence their answers instead of recalling them, which is the whole point of
// a close-reading workbook.
#let cite-field(label: "Found on page(s)") = block(above: 3mm, below: 0pt, width: 100%, align(right, {
  caps(label, size: 6.5pt, fill: faint)
  h(2.5mm)
  box(width: 22mm, place(bottom + left, dy: -0.6mm, line(length: 100%, stroke: stroke-field)))
}))

// A passage quoted from the book, so a student never confuses the book's voice
// with the tutor's question.
#let quoted(step, body) = block(
  width: 100%,
  above: 3.5mm,
  below: 0mm,
  fill: step-wash.at(step - 1),
  inset: (x: 4.5mm, y: 3.4mm),
  stroke: (left: 2pt + step-fill.at(step - 1)),
  radius: (right: 2pt),
  text(font: serif, size: size-quote, fill: ink-soft, body),
)

// The atomic unit. `breakable: false` guarantees a prompt is never separated
// from the space where its answer goes. The number hangs in the gutter outside
// the margin rule, where it aligns down the page without stealing measure from
// the prompt or from the answer lines.
#let question(number, prompt, lines: lines-medium, quote: none, cite: true) = context {
  let step = active-section().step
  block(
    breakable: false,
    width: 100%,
    above: space-between-questions,
    below: 0pt,
    {
      place(top + left, dx: gutter-dx, dy: 0.6mm, box(
        width: gutter-width,
        align(right, text(font: sans, size: 9.5pt, weight: "semibold", fill: step-deep.at(step - 1), number)),
      ))
      block(below: 0pt, prompt)
      if quote != none { quoted(step, quote) }
      v(space-prompt-to-response)
      response-lines(lines)
      if cite { cite-field() }
    },
  )
}

// --- Writing prompt ---------------------------------------------------------

#let scaffold(step, items) = block(
  width: 100%,
  above: 4mm,
  below: 0mm,
  inset: (x: 4.5mm, y: 3.6mm),
  radius: 2pt,
  fill: step-wash.at(step - 1),
  {
    caps("Before you write", size: 7pt, fill: step-deep.at(step - 1))
    v(2.4mm)
    set text(font: sans, size: 8.5pt, fill: ink-soft)
    stack(
      spacing: 1.8mm,
      ..items.map(it => grid(columns: (4mm, 1fr), text(fill: step-deep.at(step - 1))[•], it)),
    )
  },
)

// Fills whatever vertical space remains on the page with ruled lines. This
// exists because a writing surface must never break unlabelled, and an author
// cannot know where a page will break — the layout engine decides that.
#let fill-with-lines(minimum: 0) = context {
  let free = page-height - margin-bottom - surface-bottom-guard - here().position().y
  let n = calc.max(minimum, int(free / line-gap))
  block(above: 0pt, below: 0pt, response-lines(n))
}

// A writing prompt gets a page of its own, without ever forcing a page break.
// See DESIGN-DECISIONS.md — an explicit break here would strand the section band
// on the page it left behind, which is the orphan this design exists to prevent.
#let writing-prompt(number, prompt, hints: none) = {
  context {
    let step = active-section().step
    block(
      breakable: false,
      width: 100%,
      above: space-between-questions,
      below: 0pt,
      {
        place(top + left, dx: gutter-dx, dy: 0.6mm, box(
          width: gutter-width,
          align(right, text(font: sans, size: 9.5pt, weight: "semibold", fill: step-deep.at(step - 1), number)),
        ))
        block(below: 0pt, prompt)
        if hints != none { scaffold(step, hints) }
        v(space-prompt-to-response)
        block(above: 0pt, below: 0pt, response-lines(lines-writing-min))
      },
    )
  }
  // Top up the remainder of the page, seamlessly continuing the same surface.
  fill-with-lines()
}

// An additional, deliberate writing page. Labelled on both sides of the break:
// the running head says "(continued)" and the prompt is echoed here, so a
// student writing on the second page can still see what was asked.
#let writing-continuation(number, echo, step: 3, section: "Writing (continued)") = {
  pagebreak(weak: true)
  section-marker(section, step: step, force: true)
  block(sticky: true, width: 100%, above: 0mm, below: 5mm, {
    place(top + left, dx: gutter-dx, dy: 0.4mm, box(
      width: gutter-width,
      align(right, text(font: sans, size: 9.5pt, weight: "semibold", fill: step-deep.at(step - 1), number)),
    ))
    text(font: serif, size: 10.5pt, fill: muted)[#echo — continued]
  })
  fill-with-lines()
}

// --- Vocabulary -------------------------------------------------------------

// A section almost never ends level with the foot of a page, and the pages where
// one did were the emptiest in the book — a section whose last question is
// followed by a writing prompt leaves most of a sheet behind, because a writing
// surface is an unbreakable block that has to move to a page it fits on.
//
// Rather than pad the section or leave the remainder blank, the tail hands the
// space back to the student. Every use of it is a real invitation, not filler:
// close reading is the point of the book, and a student noticing something the
// questions did not ask about is the behaviour worth making room for.
//
// It renders only when enough of the page is left to be worth using, so authors
// can call it at the end of any section without ever producing a stub.
#let ruled-tail(title, minimum: 5) = context {
  let free = page-height - margin-bottom - surface-bottom-guard - here().position().y
  let n = int((free - 15mm) / line-gap)
  if n >= minimum {
    v(11mm)
    caps(title, size: 7pt, fill: faint)
    v(3.5mm)
    response-lines(n)
  }
}

#let own-words(minimum: 5) = ruled-tail("Words you met in these chapters", minimum: minimum)

#let vocab-field(label, body) = block(above: space-vocab-field, below: 0mm, grid(
  columns: (19mm, 1fr),
  column-gutter: 3.5mm,
  move(dy: 1.2pt, caps(label, size: 6.5pt)),
  text(font: serif, size: size-vocab-body, fill: ink-body, body),
))

// Entry blocks rather than table rows: each field gets the full measure, a long
// tutor definition grows without distorting its neighbours, and pagination
// happens between entries instead of inside a cell. A rule under the term line
// gives the scannability a table would have given, without the cramped columns.
#let vocab-entry(
  number,
  term,
  gloss,
  definition: none,
  from-book: none,
  excerpt-context: none,
  index: 0,
) = block(
  breakable: false,
  width: 100%,
  above: space-vocab-entry,
  below: 0mm,
  {
    // The gloss sits directly beside its term rather than ranged right. A
    // Korean meaning stranded at the far margin is a column to scan; next to
    // the word it answers the question a student is actually asking.
    place(top + left, dx: gutter-dx, dy: 1.2mm, box(
      width: gutter-width,
      align(right, text(font: sans, size: 8.5pt, weight: "semibold", fill: faint, number)),
    ))
    block(below: 0pt, {
      text(font: serif, size: size-vocab-term, weight: "bold", fill: ink, term)
      h(4mm)
      text(font: sans, size: 10pt, fill: step-deep.at(3), gloss)
    })
    v(1.8mm)
    line(length: 100%, stroke: 0.5pt + step-fill.at(3))
    if definition != none { vocab-field("Definition", definition) }
    if from-book != none { vocab-field("From book", from-book) }
    if excerpt-context != none { vocab-field("Excerpt context", excerpt-context) }
  },
)
