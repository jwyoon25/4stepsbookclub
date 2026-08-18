// ---------------------------------------------------------------------------
// Page grammar components.
//
// Each component owns one role from the design brief. Content is passed in;
// nothing here knows anything about a particular book or lesson.
//
// Pagination rules are enforced structurally, not by hand:
//   - `block(breakable: false)` keeps a question with its response area.
//   - `block(sticky: true)` keeps a heading with the content beneath it.
// ---------------------------------------------------------------------------

#import "tokens.typ": *

// --- Document state ---------------------------------------------------------

#let doc-book = state("book", "")
#let doc-lesson = state("lesson", "")
#let doc-step = state("step", 1) // which of the four steps we are inside

// Which section a page belongs to cannot use `state`: a header is laid out at
// the top of its page, before any state update made by content on that same
// page. A section beginning on page 3 would therefore never reach page 3's
// header. Instead each section drops a positioned marker, and the header works
// out which one applies by comparing page numbers.
#let section-marker(name, force: false, continued: false) = [#metadata((
  name: name, force: force, continued: continued,
))#label("wb-section")]

// A marker owns its page if it sits at the top of the text block — that is, the
// section starts the page rather than joining it partway down.
#let starts-page = margin-top + 26mm

// Precedence: a forced marker (continuation heading) > a section starting at the
// top of this page > the section still running when the page opened > any
// section starting on this page. Third before fourth is what stops a section
// beginning halfway down a page from relabelling the half above it.
#let active-section() = {
  let p = here().position().page
  let markers = query(<wb-section>)
  let on-page = markers.filter(m => m.location().position().page == p)
  let forced = on-page.filter(m => m.value.force)
  let opening = on-page.filter(m => m.location().position().y <= starts-page)
  let earlier = markers.filter(m => m.location().position().page < p)
  let carried = if earlier.len() > 0 { earlier.last().value } else { none }

  if forced.len() > 0 {
    forced.first().value.name
  } else if opening.len() > 0 {
    opening.first().value.name
  } else if carried != none and carried.name != none {
    // A section that opted in gets "(continued)" on every page after the one it
    // started on. This is how a vocabulary list announces itself across a break
    // without anyone having to know in advance where the break lands.
    if carried.continued { carried.name + " (continued)" } else { carried.name }
  } else if on-page.len() > 0 {
    on-page.first().value.name
  } else { none }
}

// --- The four-step mark -----------------------------------------------------
//
// The logo's four ascending bars, redrawn as vector so they scale and stay
// crisp. With `active` set, the current step is in its own colour and the rest
// are muted: the brand mark and the progress indicator are the same object.

#let step-bars(active: 0, size: 6mm) = {
  let ratios = (0.50, 0.68, 0.84, 1.00)
  let bw = size * 0.25
  let gap = size * 0.12
  box(width: 4 * bw + 3 * gap, height: size, baseline: 0pt, {
    for i in range(4) {
      place(
        bottom + left,
        dx: i * (bw + gap),
        rect(
          width: bw,
          height: size * ratios.at(i),
          fill: if active == i + 1 { step-colors.at(i) } else { step-muted },
          radius: bw * 0.32,
          stroke: none,
        ),
      )
    }
  })
}

// --- Layout helpers ---------------------------------------------------------

#let caps(body, size: size-label, weight: "semibold", fill: ink-faint, tracking: tracking-caps) = text(
  font: sans, size: size, weight: weight, fill: fill, tracking: tracking, upper(body),
)

// Question numbers hang in a narrow indent so the numbers align down the page
// while the prompt still starts near the left margin.
#let hanging(marker, body) = grid(
  columns: (hang, 1fr), column-gutter: 0pt, marker, body,
)

// --- Page furniture ---------------------------------------------------------

// Every page carries the mark. Weight is inverse to how much writing happens on
// the page: full lockup on covers, a small mark in the furniture everywhere
// else, and a very pale mark behind the page.
#let page-watermark() = context {
  if active-section() != none {
    place(
      center + horizon,
      dy: 6mm,
      box(width: watermark-size, image(logo-watermark, width: 100%)),
    )
  }
}

#let running-head() = context {
  let section = active-section()
  if section != none {
    grid(
      columns: (auto, 1fr, auto),
      column-gutter: 3mm,
      align: horizon,
      step-bars(active: doc-step.get(), size: 4mm),
      text(font: sans, size: size-furniture, fill: ink-faint, doc-book.get()),
      text(font: sans, size: size-furniture, weight: "semibold", fill: ink-soft, section),
    )
  }
}

#let running-foot() = context {
  let section = active-section()
  let total = counter(page).final().first()
  let current = counter(page).at(here()).first()

  if section == none {
    // Covers: the wordmark, centred, as the page's closing mark.
    align(center, box(width: 38mm, image(logo-wordmark, width: 100%)))
  } else {
    grid(
      columns: (auto, 1fr, auto),
      column-gutter: 3mm,
      align: horizon,
      box(width: 26mm, image(logo-wordmark, width: 100%)),
      text(font: sans, size: size-furniture, fill: ink-faint, doc-lesson.get()),
      text(font: sans, size: size-furniture, fill: ink-faint)[Page #current of #total],
    )
  }
}

// --- Document wrapper -------------------------------------------------------

#let workbook(book: "", lesson: "", body) = {
  set page(
    paper: paper,
    margin: (top: margin-top, bottom: margin-bottom, x: margin-x),
    header: running-head(),
    header-ascent: head-ascent,
    footer: running-foot(),
    footer-descent: foot-descent,
    background: page-watermark(),
  )
  set text(font: serif, size: size-body, fill: ink, lang: "en")
  // Ragged right: at this measure justification opens rivers, and prompts read
  // better with an even word space.
  set par(leading: leading-body, justify: false)

  doc-book.update(book)
  doc-lesson.update(lesson)
  body
}

// --- Covers -----------------------------------------------------------------

#let name-date-fields(width: 88mm) = {
  let field(label) = box(width: 100%, height: 8mm, {
    place(bottom + left, dy: -1.9mm, caps(label, fill: ink-soft))
    place(bottom + left, dx: 17mm, line(length: 100% - 17mm, stroke: stroke-ruled))
  })
  block(width: width, {
    field("Name")
    v(4mm)
    field("Date")
  })
}

#let workbook-cover(book: "", author: "", series: "", span: "") = {
  section-marker(none)
  v(20mm)
  box(width: 62mm, image(logo-full, width: 100%))
  v(20mm)
  caps(series, size: 9pt, fill: brand-orange)
  v(7mm)
  text(font: serif-display, size: size-cover-title, weight: "semibold", fill: ink, book)
  v(3mm)
  text(font: serif, size: 12pt, style: "italic", fill: ink-soft, author)
  v(6mm)
  step-bars(active: 0, size: 9mm)
  v(6mm)
  text(font: sans, size: 10.5pt, fill: brand-navy, span)
  v(1fr)
  name-date-fields()
  v(3mm)
  pagebreak()
}

// The lesson cover absorbs what would otherwise be a separate lesson opener:
// a single lesson is often handed out on its own, so it needs its own identity,
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
  v(10mm)
  grid(
    columns: (1fr, auto),
    align: horizon,
    caps(lesson, size: 11pt, fill: brand-orange),
    box(width: 34mm, image(logo-full, width: 100%)),
  )
  // Slack is split above and below the content block rather than pooled into a
  // single gap; an even division reads as composition, one big hole reads as a
  // mistake.
  v(1fr)
  text(font: serif-display, size: size-lesson-title, weight: "semibold", fill: ink, title)
  v(2.5mm)
  text(font: serif, size: 11.5pt, style: "italic", fill: ink-soft, chapters)
  v(7mm)
  block(width: 148mm, text(size: size-body, fill: ink-soft, framing))

  // The four steps of this lesson, shown as the mark itself.
  if sections.len() > 0 {
    v(9mm)
    caps("The four steps in this lesson", fill: ink-faint)
    v(4mm)
    block(width: 100%, grid(
      columns: (1fr,) * sections.len(),
      column-gutter: 4mm,
      ..sections.enumerate().map(((i, s)) => {
        block(
          width: 100%,
          inset: (x: 3mm, y: 3mm),
          radius: 2pt,
          fill: step-colors.at(i).lighten(90%),
          stroke: (left: 2pt + step-colors.at(i)),
          {
            caps("Step " + str(i + 1), size: 7pt, fill: step-colors.at(i))
            v(1.4mm)
            text(font: sans, size: 9pt, weight: "semibold", fill: ink, s)
          },
        )
      }),
    ))
  }

  // Name, date, and the standing note form a deliberate footer group. The rule
  // above them turns what would otherwise read as a void in the middle of the
  // page into an intentional division.
  v(1fr)
  line(length: 100%, stroke: stroke-hairline)
  v(7mm)
  grid(
    columns: (1fr, 1fr),
    column-gutter: 10mm,
    name-date-fields(width: 100%),
    if note != none {
      block(
        width: 100%,
        inset: (x: 3.5mm, y: 3mm),
        radius: 2pt,
        fill: tint-quote,
        text(font: sans, size: 8pt, fill: ink-soft, note),
      )
    },
  )
  v(2mm)
  pagebreak()
}

// --- Section band -----------------------------------------------------------
//
// `sticky: true` is the anti-orphan rule: a band can never end a page, it is
// carried to the next page along with whatever follows it.

#let section-band(step, name, description, continued-label: false) = {
  section-marker(name, continued: continued-label)
  doc-step.update(step)
  let c = step-colors.at(step - 1)
  block(
    sticky: true,
    width: 100%,
    above: space-band-above,
    below: space-band-below,
    inset: (x: 4mm, y: 3.4mm),
    radius: 2pt,
    fill: c.lighten(91%),
    stroke: (left: 2.5pt + c),
    grid(
      columns: (auto, 1fr),
      column-gutter: 4.5mm,
      align: horizon,
      step-bars(active: step, size: 7mm),
      {
        caps("Step " + str(step) + " — " + name, size: size-band, fill: c)
        v(1.2mm)
        text(font: sans, size: 8.5pt, fill: ink-soft, description)
      },
    ),
  )
}

// --- Question unit ----------------------------------------------------------

#let response-lines(n) = stack(
  spacing: 0pt,
  ..range(n).map(_ => box(
    width: 100%,
    height: line-gap,
    place(bottom + left, line(length: 100%, stroke: stroke-ruled)),
  )),
)

// Where in the book the answer came from. Carried over from the existing 4steps
// workbook, where every question has a "page(s):" field — it makes students
// evidence their answers instead of recalling them, which is the whole point of
// a close-reading workbook.
#let cite-field(label: "Found on page(s)") = block(above: 3.2mm, below: 0pt, width: 100%, align(right, {
  caps(label, size: 7pt, fill: ink-faint)
  h(2mm)
  box(width: 20mm, place(bottom + left, dy: -0.6mm, line(length: 100%, stroke: 0.5pt + hairline)))
}))

// A passage quoted from the book, so a student never confuses the book's voice
// with the tutor's question.
#let quoted(body) = context block(
  width: 100%,
  above: 3mm,
  below: 0mm,
  fill: tint-quote,
  inset: (x: 4mm, y: 3mm),
  stroke: (left: 1.5pt + step-colors.at(doc-step.get() - 1)),
  radius: 1.5pt,
  text(font: serif, size: size-quote, fill: ink-soft, body),
)

// The atomic unit. `breakable: false` guarantees a prompt is never separated
// from the space where its answer goes.
#let question(number, prompt, lines: lines-medium, quote: none, cite: true) = context block(
  breakable: false,
  width: 100%,
  above: space-between-questions,
  below: 0pt,
  {
    hanging(
      text(font: sans, size: 10.5pt, weight: "bold", fill: step-colors.at(doc-step.get() - 1))[#number)],
      block(below: 0pt, prompt),
    )
    if quote != none { quoted(quote) }
    v(space-prompt-to-response)
    response-lines(lines)
    if cite { cite-field() }
  },
)

// --- Writing prompt ---------------------------------------------------------

#let scaffold(items) = context block(
  width: 100%,
  above: 3.5mm,
  below: 0mm,
  inset: (x: 4mm, y: 3.4mm),
  radius: 2pt,
  fill: step-colors.at(doc-step.get() - 1).lighten(94%),
  stroke: 0.5pt + step-colors.at(doc-step.get() - 1).lighten(60%),
  {
    caps("Before you write", size: 7.5pt, fill: step-colors.at(doc-step.get() - 1))
    v(2.2mm)
    set text(font: sans, size: 8.5pt, fill: ink-soft)
    stack(
      spacing: 1.6mm,
      ..items.map(it => grid(columns: (3.5mm, 1fr), text(fill: ink-faint)[•], it)),
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
  context block(
    breakable: false,
    width: 100%,
    above: space-between-questions,
    below: 0pt,
    {
      hanging(
        text(font: sans, size: 10.5pt, weight: "bold", fill: step-colors.at(doc-step.get() - 1))[#number)],
        block(below: 0pt, prompt),
      )
      if hints != none { scaffold(hints) }
      v(space-prompt-to-response)
      block(above: 0pt, below: 0pt, response-lines(lines-writing-min))
    },
  )
  // Top up the remainder of the page, seamlessly continuing the same surface.
  fill-with-lines()
}

// An additional, deliberate writing page. Labelled on both sides of the break:
// the running head says "(continued)" and the prompt is echoed here, so a
// student writing on the second page can still see what was asked.
#let writing-continuation(number, echo, section: "Writing (continued)") = {
  pagebreak(weak: true)
  section-marker(section, force: true)
  context block(sticky: true, width: 100%, above: 0mm, below: 4mm, hanging(
    text(font: sans, size: 10.5pt, weight: "bold", fill: step-colors.at(doc-step.get() - 1))[#number)],
    text(font: serif, size: 10pt, style: "italic", fill: ink-soft)[#echo — continued],
  ))
  fill-with-lines()
}

// --- Vocabulary -------------------------------------------------------------

#let vocab-field(label, body) = block(above: space-vocab-field, below: 0mm, grid(
  columns: (19mm, 1fr),
  column-gutter: 3mm,
  move(dy: 1.1pt, caps(label, size: 7pt)),
  text(font: serif, size: size-vocab-body, fill: ink, body),
))

// Entry blocks rather than table rows: each field gets the full measure, a long
// tutor definition grows without distorting its neighbours, and pagination
// happens between entries instead of inside a cell. Alternating tint gives the
// scannability a table would have given, without the cramped columns.
#let vocab-entry(
  number,
  term,
  gloss,
  definition: none,
  in-context: none,
  from-book: none,
  index: 0,
) = block(
  breakable: false,
  width: 100%,
  above: space-vocab-entry,
  below: 0mm,
  inset: (x: 3.5mm, y: 3mm),
  radius: 2pt,
  fill: if calc.rem(index, 2) == 0 { tint-row } else { none },
  {
    // The gloss sits directly beside its term rather than ranged right. A
    // Korean meaning stranded at the far margin is a column to scan; next to
    // the word it answers the question a student is actually asking.
    block(below: 0pt, {
      text(font: sans, size: 8pt, weight: "bold", fill: brand-teal)[#number]
      h(3mm)
      text(font: serif, size: size-vocab-term, weight: "semibold", fill: ink, term)
      h(4mm)
      text(font: gloss-stack, size: 10.5pt, fill: brand-navy, gloss)
    })
    v(2.4mm)
    if definition != none { vocab-field("Definition", definition) }
    if in-context != none { vocab-field("In context", in-context) }
    if from-book != none { vocab-field("From book", from-book) }
  },
)
