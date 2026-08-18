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
#let doc-edition = state("edition", "Student")

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
// was already running, which left pages carrying one section band under another
// section's active tab
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
        fill: if on { step-fill.at(i) } else { step-pale.at(i) },
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
    if section.step >= 1 and section.step <= 4 { section-tabs(section.step) }
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
  let lesson-label = doc-lesson.get()
  let centre-label = if doc-edition.get() == "Teacher" {
    if lesson-label == "" { "Teacher guide" } else { lesson-label + " · Teacher guide" }
  } else {
    lesson-label
  }
  grid(
    columns: (auto, 1fr, auto),
    column-gutter: 4mm,
    align: horizon,
    wordmark(),
    text(font: sans, size: size-furniture, fill: faint, centre-label),
    text(font: sans, size: size-furniture, fill: faint)[Page #current of #total],
  )
}

// --- Document wrapper -------------------------------------------------------

#let workbook(book: "", lesson: "", edition: "Student", body) = {
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
  doc-edition.update(edition)
  body
}

#let lesson-start(lesson) = doc-lesson.update(lesson)

// --- Covers -----------------------------------------------------------------
//
// Covers share a full-height four-step rail. Workbook covers name the method in
// the rail; lesson covers keep the same structure but leave the bands quiet.
#let cover-paper(show-labels: false) = {
  place(top + left, dx: -margin-left, dy: -margin-top, rect(
    width: page-width, height: page-height, fill: white, stroke: none,
  ))
  let band-height = page-height / 4
  let short-names = ("Comprehension", "Analysis", "Writing", "Vocabulary")
  for i in range(4) {
    place(top + left, dx: -margin-left, dy: -margin-top + i * band-height, rect(
      width: cover-rail-width, height: band-height, fill: step-pale.at(i), stroke: none,
    ))
    if show-labels {
      place(
        top + left,
        dx: -margin-left,
        dy: -margin-top + i * band-height,
        box(
          width: cover-rail-width,
          height: band-height,
          align(center + horizon, rotate(
            -90deg,
            origin: center,
            box(width: 66mm, align(center, {
              text(
                font: sans, size: 10pt, weight: "semibold", fill: ink,
                tracking: 0.18em, upper(str(i + 1) + "  " + step-actions.at(i)),
              )
              h(2mm)
              text(
                font: sans, size: 10pt, weight: "semibold", fill: muted,
                tracking: 0.18em, upper("— " + short-names.at(i)),
              )
            })),
          )),
        ),
      )
    }
  }
}

#let cover-rule() = place(
  top + left,
  dx: cover-content-left - margin-left,
  dy: 57mm - margin-top,
  line(length: page-width - cover-content-left - cover-content-right, stroke: 0.4mm + coral-deep),
)

#let cover-site-mark() = grid(
  columns: (7mm, auto),
  column-gutter: 1.5mm,
  align: horizon,
  image(logomark-small, width: 7mm),
  text(font: sans, size: 10pt, fill: muted, tracking: 0.04em, "4stepsbookclub.com"),
)

#let workbook-cover(
  book: "",
  author: "",
  series: "",
  span: "",
  subtitle: none,
  edition: "Student",
) = {
  section-marker(none)
  cover-paper(show-labels: true)
  cover-rule()
  place(
    top + left,
    dx: cover-content-left - margin-left,
    dy: 22mm - margin-top,
    image(logotype, width: cover-logo-width),
  )
  place(
    top + left,
    dx: 110mm - margin-left,
    dy: 22mm - margin-top,
    box(
      width: page-width - 110mm - cover-content-right,
      height: 27.5mm,
      inset: (top: 3.5mm, bottom: 2mm),
      align(right, grid(
        columns: (1fr,), rows: (auto, 1fr, auto), align: right,
        caps(series, size: size-cover-series),
        [],
        caps(span, size: size-cover-series),
      )),
    ),
  )
  if edition == "Teacher" {
    place(
      top + left,
      dx: 144mm - margin-left,
      dy: 39mm - margin-top,
      box(
        inset: (x: 3mm, y: 1.8mm),
        radius: 2pt,
        fill: step-wash.at(1),
        stroke: 0.6pt + coral-deep,
        caps("Teacher guide", size: 7pt, fill: coral-deep),
      ),
    )
  }
  place(
    top + left,
    dx: cover-content-left - margin-left,
    dy: 74mm - margin-top,
    box(width: page-width - cover-content-left - 34mm, text(
      font: serif, size: size-cover-title, weight: "bold", fill: ink, book,
    )),
  )
  place(
    top + left,
    dx: cover-content-left - margin-left,
    dy: 134mm - margin-top,
    text(font: serif, size: 14pt, fill: muted, author),
  )
  if subtitle != none {
    place(
      top + left,
      dx: cover-content-left - margin-left,
      dy: 153mm - margin-top,
      box(width: 124mm, text(font: sans, size: 10pt, fill: ink-soft, subtitle)),
    )
  }
  place(bottom + right, dy: -6mm, cover-site-mark())
  pagebreak()
}

#let instruction-row(title, body) = grid(
  columns: (38mm, 1fr),
  column-gutter: 5mm,
  align: top,
  text(font: sans, size: 9.5pt, weight: "semibold", fill: ink, title),
  text(font: sans, size: 9.5pt, fill: muted, body),
)

#let how-to-step(step, name, description) = grid(
  columns: (15mm, 34mm, 1fr),
  column-gutter: 5mm,
  align: top,
  rect(width: 15mm, height: 8.5mm, fill: step-fill.at(step - 1), radius: (right: tab-radius)),
  stack(spacing: 1mm,
    text(font: sans, size: 9.5pt, weight: "semibold", fill: ink, str(step) + "  " + step-actions.at(step - 1)),
    text(font: sans, size: 8pt, fill: faint, name),
  ),
  text(font: sans, size: 9.5pt, fill: muted, description),
)

#let how-to-page() = {
  // An empty section name keeps the running rule, book title, footer, and page
  // number while leaving the right side of the running head deliberately blank.
  section-marker("", step: 0, force: true)
  place(top + left, dy: 0mm,
    text(font: serif, size: 24pt, weight: "bold", fill: ink, "How to use this workbook"),
  )
  place(top + left, dy: 14.5mm,
    block(width: 122mm, text(font: serif, size: 11pt, fill: ink-body)[Each lesson covers a set of chapters and moves through four steps. Read the chapters once for the story, then work through the questions with the book open beside you.]),
  )
  place(top + left, dy: 44mm, caps("Choosing how to answer"))
  place(top + left, dy: 50.6mm, stack(
    spacing: 3.5mm,
    instruction-row("Print and handwrite", [Write on the ruled lines and follow any *Guidance & requirements* box attached to the question. The space provided is chosen by your tutor.]),
    instruction-row("Annotate the PDF", [Use GoodNotes or another app that lets you write directly on the ruled lines.]),
    instruction-row("Type in Google Docs", [Label each answer with its lesson, section, and question code so your tutor can match it to the workbook.]),
  ))
  place(top + left, dy: 91.7mm, block(
    width: 100%,
    inset: (x: 6mm, y: 5mm),
    radius: 2pt,
    fill: canvas,
    stroke: stroke-hairline,
    grid(
      columns: (auto, 1fr),
      column-gutter: 7mm,
      stack(
        spacing: 2mm,
        text(font: serif, size: 17pt, weight: "bold", fill: coral-deep, "L3-C2"),
        text(font: sans, size: 7pt, fill: faint, tracking: 0.06em, "Lesson 3 · Comprehension · 2"),
      ),
      text(font: sans, size: 9pt, fill: ink-soft)[Use *C* for Comprehension, *A* for Analysis, and *W* for Writing. Questions restart at 1 in every section. When you quote or point to a detail, cite the page inside your response—for example, *(p. 47)*.],
    ),
  ))
  place(top + left, dy: 132mm, caps("The four steps"))
  place(top + left, dy: 139.2mm, stack(
    spacing: 3.2mm,
    how-to-step(1, "Comprehension", [Answer from the text. Keep factual responses concise and cite supporting pages in parentheses.]),
    how-to-step(2, "Analysis", [Interpret the reading, explain your reasoning, and point to specific evidence.]),
    how-to-step(3, "Writing", [Develop a claim, support it with evidence, and explain the connection.]),
    how-to-step(4, "Vocabulary", [Return to important words and the moments in which they appear in the reading.]),
  ))
  pagebreak()
}

// The lesson cover absorbs what would otherwise be a separate lesson opener: a
// single lesson is often handed out on its own, so it needs its own identity,
// identity and orientation.
#let lesson-cover(
  lesson: "",
  title: "",
  chapters: "",
  framing: "",
  instructions: none,
  sections: (),
  note: none,
  edition: "Student",
) = {
  pagebreak(weak: true)
  section-marker(none)
  cover-paper()
  cover-rule()
  let cover-kind = if edition == "Teacher" { "Teacher guide · Reading workbook" } else { "Reading workbook" }
  place(
    top + left,
    dx: cover-content-left - margin-left,
    dy: 22mm - margin-top,
    box(
      height: 27.5mm,
      inset: (top: 3.5mm, bottom: 2mm),
      grid(
        columns: (auto,), rows: (auto, 1fr, auto),
        caps(lesson, size: 11pt, fill: coral-deep, tracking: 0.16em),
        [],
        caps(cover-kind, size: 8.5pt, tracking: 0.16em),
      ),
    ),
  )
  place(
    top + left,
    dx: 132mm - margin-left,
    dy: 22mm - margin-top,
    image(logotype, width: cover-logo-width),
  )
  place(top + left, dx: cover-content-left - margin-left, dy: 80mm - margin-top,
    box(width: page-width - cover-content-left - cover-content-right, height: 118mm, {
      place(top + left,
        box(width: 124mm, text(font: serif, size: size-lesson-title, weight: "bold", fill: ink, title)),
      )
      place(top + left, dy: 12.8mm,
        text(font: serif, size: 12pt, fill: muted, chapters),
      )
      place(top + left, dy: 26.3mm,
        block(width: 124mm, text(font: serif, size: size-body, fill: ink-body, framing)),
      )

      if instructions != none {
        place(top + left, dy: 51mm, block(
          width: 124mm,
          inset: (x: 4mm, y: 3.2mm),
          radius: 2pt,
          fill: canvas,
          stroke: stroke-hairline,
          {
            caps("For this lesson", size: 7pt, fill: coral-deep)
            v(1.6mm)
            text(font: sans, size: 8.5pt, fill: ink-soft, instructions)
          },
        ))
      }

      // The four sections of this lesson, shown as the tabs they will appear as.
      if sections.len() > 0 {
        let section-top = if instructions == none { 55.8mm } else { 76mm }
        place(top + left, dy: section-top, caps("In this lesson", fill: muted))
        place(top + left, dy: section-top + 7.1mm, block(width: 100%, stack(
          spacing: 3.5mm,
          ..sections.enumerate().map(((i, s)) => grid(
            columns: (tab-width-active, 1fr),
            column-gutter: 5mm,
            align: horizon,
            rect(
              width: tab-width-active, height: tab-height,
              fill: step-fill.at(i), radius: (right: tab-radius), stroke: none,
            ),
            {
              text(font: sans, size: 9.5pt, weight: "semibold", fill: ink, s.name)
              h(2mm)
              text(font: sans, size: 9.5pt, fill: muted,
                "·  Step " + str(i + 1) + " " + step-actions.at(i) + "  ·  " + s.detail)
            },
          )),
        )))
      }
    }),
  )

  if note != none {
    place(bottom + left, dx: cover-content-left - margin-left, dy: -6mm,
      block(
        width: page-width - cover-content-left - cover-content-right,
        inset: (x: 4mm, y: 3.4mm),
        radius: 2pt,
        fill: canvas,
        stroke: stroke-hairline,
        text(font: sans, size: 8.5pt, fill: ink-soft, note),
      ),
    )
  }
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
    box(width: 100%, height: 23.5mm, {
      place(top + left, dx: -overhang, rect(
        width: block-width + overhang, height: band-bar-height,
        fill: c, radius: (right: tab-radius), stroke: none,
      ))
      place(top + left, dy: 6mm,
        caps("Step " + str(step) + "  ·  " + step-actions.at(step - 1), size: size-furniture, fill: step-deep.at(step - 1)),
      )
      place(top + left, dy: 10.4mm,
        text(font: serif, size: size-section-title, weight: "bold", fill: ink, name),
      )
      place(top + left, dy: 19.1mm,
        block(width: 126mm, text(font: sans, size: 8.5pt, fill: muted, description)),
      )
    }),
  )
}

// --- Question unit ----------------------------------------------------------
//
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

// Tutor-authored directions that are part of the question in both editions.
// A list keeps separate requirements scannable and gives the future editor one
// repeatable control for length, structure, quotation, and evidence guidance.
#let response-guidance-panel(step, items) = block(
  width: 100%,
  above: 4mm,
  below: 0mm,
  inset: (x: 4.5mm, y: 3.6mm),
  radius: 2pt,
  fill: step-wash.at(step - 1),
  {
    caps("Guidance & requirements", size: 7pt, fill: step-deep.at(step - 1))
    v(2.4mm)
    set text(font: sans, size: 8.5pt, fill: ink-soft)
    stack(
      spacing: 1.8mm,
      ..items.map(it => grid(columns: (4mm, 1fr), text(fill: step-deep.at(step - 1))[•], it)),
    )
  },
)

#let teacher-panel(label, body) = context {
  let step = active-section().step
  block(
    width: 100%,
    above: 3.5mm,
    below: 0mm,
    fill: step-wash.at(step - 1),
    inset: (x: 4.5mm, y: 3.4mm),
    stroke: (left: 2pt + step-deep.at(step - 1)),
    radius: (right: 2pt),
    {
      caps(label, size: 7pt, fill: step-deep.at(step - 1))
      v(1.8mm)
      text(font: serif, size: 9.5pt, fill: ink-body, body)
    },
  )
}

// The atomic unit. `breakable: false` guarantees a prompt is never separated
// from the space where its answer goes. The number hangs in the gutter outside
// the margin rule, where it aligns down the page without stealing measure from
// the prompt or from the answer lines.
#let question(
  number,
  prompt,
  lines: lines-medium,
  quote: none,
  response-guidance: none,
  teacher: false,
  teacher-guidance: none,
  rubric: none,
) = context {
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
      if response-guidance != none { response-guidance-panel(step, response-guidance) }
      if teacher {
        if teacher-guidance != none { teacher-panel("Teacher guidance", teacher-guidance) }
        if rubric != none { teacher-panel("Example structure / rubric", rubric) }
        if teacher-guidance == none and rubric == none {
          teacher-panel("Teacher guidance", [No additional guidance was provided for this prompt.])
        }
      } else {
        v(space-prompt-to-response)
        response-lines(lines)
      }
    },
  )
}

// --- Writing prompt ---------------------------------------------------------

// Fills whatever vertical space remains on the page with ruled lines. This
// exists because a writing surface must never break unlabelled, and an author
// cannot know where a page will break — the layout engine decides that.
#let fill-with-lines(minimum: 0, safety-lines: 0) = context {
  let free = page-height - margin-bottom - surface-bottom-guard - here().position().y
  let n = calc.max(minimum, int(free / line-gap) - safety-lines)
  block(above: 0pt, below: 0pt, response-lines(n))
}

// A writing prompt gets a page of its own, without ever forcing a page break.
// See DESIGN-DECISIONS.md — an explicit break here would strand the section band
// on the page it left behind, which is the orphan this design exists to prevent.
#let writing-prompt(
  number,
  prompt,
  response-guidance: none,
  quote: none,
  bottom-safety-lines: 0,
) = {
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
        if quote != none { quoted(step, quote) }
        if response-guidance != none { response-guidance-panel(step, response-guidance) }
        v(space-prompt-to-response)
        block(above: 0pt, below: 0pt, response-lines(lines-writing-min))
      },
    )
  }
  // Top up the remainder of the page, seamlessly continuing the same surface.
  fill-with-lines(safety-lines: bottom-safety-lines)
}

// An additional, deliberate writing page. Labelled on both sides of the break:
// the running head says "(continued)" and the prompt is echoed here, so a
// student writing on the second page can still see what was asked.
#let response-continuation(
  number,
  echo,
  step: 3,
  section: "Paragraph Writing (continued)",
  lines: none,
  break-before: true,
  bottom-safety-lines: 0,
) = {
  if break-before { pagebreak(weak: true) }
  section-marker(section, step: step, force: true)
  block(sticky: true, width: 100%, above: 0mm, below: 5mm, {
    place(top + left, dx: gutter-dx, dy: 0.4mm, box(
      width: gutter-width,
      align(right, text(font: sans, size: 9.5pt, weight: "semibold", fill: step-deep.at(step - 1), number)),
    ))
    text(font: serif, size: 10.5pt, fill: muted)[#echo — continued]
  })
  if lines == none {
    fill-with-lines(safety-lines: bottom-safety-lines)
  } else {
    response-lines(lines)
  }
}

#let writing-continuation(number, echo, step: 3, section: "Paragraph Writing (continued)") = response-continuation(
  number,
  echo,
  step: step,
  section: section,
  break-before: false,
)

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
  // Keep two lines of safety below the calculated surface. Filling the exact
  // remainder makes Typst's final page counter observe a phantom trailing page
  // even though the PDF renderer elides that empty page; one line is not enough
  // once the label and block spacing are rounded during layout.
  let n = int((free - 15mm) / line-gap) - 2
  if n >= minimum {
    v(11mm)
    caps(title, size: 7pt, fill: faint)
    v(3.5mm)
    response-lines(n)
  }
}

#let own-words(minimum: 5) = ruled-tail("Words you met in these chapters", minimum: minimum)

#let vocab-field(label, body) = {
  v(space-vocab-field)
  block(
    below: 0mm,
    inset: (bottom: 1.55mm),
    grid(
      columns: (19mm, 1fr),
      column-gutter: 3.5mm,
      move(dy: 1.2pt, caps(label, size: 6.5pt)),
      text(font: serif, size: size-vocab-body, fill: ink-body, body),
    ),
  )
}

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
  chapter-reference: none,
  index: 0,
) = block(
  breakable: false,
  width: 100%,
  above: 0mm,
  below: 0mm,
  {
    v(space-vocab-entry)
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
    if chapter-reference != none { vocab-field("Chapter", chapter-reference) }
  },
)
