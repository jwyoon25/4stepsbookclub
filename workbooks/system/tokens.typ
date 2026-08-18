// ---------------------------------------------------------------------------
// Design tokens.
//
// Every measurement, colour, and type size used by the workbook lives here.
// Components must not hard-code values; change a workbook's feel by editing
// this file, not the components.
//
// Rationale is recorded in workbooks/DESIGN-DECISIONS.md.
// ---------------------------------------------------------------------------

// --- Brand ------------------------------------------------------------------
//
// Taken from the actual logo (website/public/images/logo.png), not from the
// site's CSS. The mark is four ascending bars — navy, green, orange, teal —
// which is the "4 steps" of the business name.
//
// The workbook uses that literally: each lesson section IS one of the four
// steps and carries that step's colour. The bar device on every section header
// doubles as a progress indicator, so a student can see how far through the
// lesson they are without counting pages.

#let brand-navy = rgb("#1e3b56")
#let brand-green = rgb("#5a9b4b")
#let brand-orange = rgb("#e08a2e")
#let brand-teal = rgb("#4a8b9a")

#let step-colors = (brand-navy, brand-green, brand-orange, brand-teal)
#let step-muted = rgb("#d5dbe1") // inactive bars

// --- Ink --------------------------------------------------------------------
//
// Grayscale legibility is load-bearing: colour never carries meaning on its
// own. Every section is also named in words and numbered, so the four step
// colours are reinforcement, not the signal.

#let ink = rgb("#1c2b3a") // body text
#let ink-soft = rgb("#4a5b6b") // descriptions, secondary
#let ink-faint = rgb("#8496a6") // field labels, quiet furniture
#let hairline = rgb("#ccd6de")
#let ruled = rgb("#9fb0bf") // handwriting guide lines
#let tint-quote = rgb("#f4f7f9") // quoted book passages
#let tint-row = rgb("#f7f9fa") // alternating vocabulary rows

// --- Watermark --------------------------------------------------------------
//
// Present on every page, but never behind a writing surface at a strength that
// competes with pencil. The reference workbook's repeated diagonal text is
// exactly what not to do.

// Typst cannot fade an image inline, so the transparency is baked into a
// dedicated asset. To change it, re-run the alpha step in DESIGN-DECISIONS.md
// rather than editing a number here.
#let watermark-size = 72mm

// --- Typefaces --------------------------------------------------------------
//
// All OFL, embeddable, and vendored in workbooks/assets/fonts so builds are
// reproducible on any machine.

#let serif = "Source Serif 4"
#let serif-display = "Source Serif 4 Display"
#let sans = "Source Sans 3"
#let korean = "Pretendard Std"
#let gloss-stack = (serif, korean)

// --- Type scale -------------------------------------------------------------

#let size-cover-title = 27pt
#let size-lesson-title = 23pt
#let size-band = 10.5pt
#let size-body = 10.5pt // prompts — the reading size of the workbook
#let size-quote = 9.5pt
#let size-vocab-term = 12pt
#let size-vocab-body = 9.5pt
#let size-label = 7.5pt
#let size-furniture = 8pt

#let tracking-caps = 0.07em

// --- Page geometry ----------------------------------------------------------
//
// A4. Margins are symmetric across every page: the layout never depends on
// whether a sheet is printed left- or right-hand, because students print these
// themselves, often single-sided.
//
// There is no margin rail. An earlier draft reserved one for question numbers
// and annotation; it cost 18mm off every answer line and pushed the whole text
// block right, for space students had not asked for. Question numbers hang in a
// narrow indent instead, and response lines run the full width of the block.

#let paper = "a4"
#let page-width = 210mm
#let page-height = 297mm
#let margin-top = 19mm
#let margin-bottom = 17mm
#let margin-x = 20mm

#let head-ascent = 9mm
#let foot-descent = 8mm

#let block-width = page-width - 2 * margin-x
#let body-height = page-height - margin-top - margin-bottom

// Hanging indent for question numbers.
#let hang = 8mm

// --- Vertical rhythm --------------------------------------------------------

#let leading-body = 0.68em
#let space-prompt-to-response = 0mm
#let space-between-questions = 5.5mm
#let space-band-above = 8mm
#let space-band-below = 5mm

#let space-vocab-field = 2.4mm
#let space-vocab-entry = 4mm

// --- Handwriting response areas ---------------------------------------------
//
// 8.5mm suits a teenage hand. This is the single number most likely to need
// changing after the first real print with real students.

#let line-gap = 8.5mm
#let stroke-ruled = 0.5pt + ruled
#let stroke-hairline = 0.4pt + hairline

// Named response sizes, in ruled lines.
#let lines-short = 3
#let lines-medium = 4
#let lines-extended = 6

// Writing surfaces fill the page they start on. This minimum is what makes that
// happen: prompt, scaffold, and this many lines form one unbreakable block, too
// tall to land low on a page, so it moves to a fresh one and is then topped up
// to the footer. No explicit page break is needed — so nothing above it can be
// orphaned.
#let lines-writing-min = 14

// Keeps a filled surface clear of the footer.
#let surface-bottom-guard = 3mm

// --- Assets -----------------------------------------------------------------

#let logo-full = "/assets/logo/logo-full.png"
#let logo-wordmark = "/assets/logo/logo-wordmark.png"
#let logo-watermark = "/assets/logo/logo-watermark.png"
