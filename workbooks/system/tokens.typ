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
// Taken from the website's design tokens (website/src/components/SiteChrome.astro)
// and the logo SVGs, so the workbook and the site cannot drift apart.
//
// The workbook uses the brand's editorial palette and paper-rule motif without
// imitating a notebook on every surface. White pages keep home printing clean;
// the rust spine and four method colours provide the recurring identity.

#let ink = rgb("#17342f") // forest green; the brand's black
#let ink-soft = rgb("#24483f")
#let ink-body = rgb("#263a34")
#let muted = rgb("#5f7069")
#let faint = rgb("#69786f") // small labels and quiet furniture; 4.65:1 on white

#let paper = rgb("#f7f3ea") // warm neutral for restrained callouts
#let paper-deep = rgb("#eee7da")
#let canvas = rgb("#fffdf8")

#let coral = rgb("#ef6b4a")
#let coral-deep = rgb("#b84431") // the margin rule
#let line-soft = rgb("#dfe4dc")

// --- Section colours --------------------------------------------------------
//
// The four section colours are the brand's method palette. The sections keep
// their working names — Comprehension, Analysis, Writing, Vocabulary — because
// that is what is actually on the page; the palette is what ties them to the
// READ · THINK · SPEAK · WRITE method.
//
// `step-actions` assigns a verb per section, in book order, so the verb printed
// beside a section is the verb for that section — not the verb that happens to
// share its index in the brand's strip. Paragraph Writing is WRITE. Vocabulary
// is SPEAK. Provisional: see "Step verbs" in DESIGN-DECISIONS.md.
//
// These are pastels. They are fills, never text: every one of them fails
// contrast as type on white. Each has a `-deep` partner for the rare place a
// section has to be named in its own colour.

#let step-fill = (rgb("#a9cdb0"), rgb("#f0b6a4"), rgb("#96cdc9"), rgb("#bfb2dc"))
#let step-deep = (rgb("#4f7d5b"), rgb("#a9503a"), rgb("#3a7570"), rgb("#6d5c99"))
#let step-wash = (rgb("#f0f5ef"), rgb("#fdf0ec"), rgb("#eff8f7"), rgb("#f3f0f8"))
#let step-pale = (rgb("#e4ede3"), rgb("#f7ddd5"), rgb("#dcf0ed"), rgb("#e8e2f1"))
#let step-actions = ("Read", "Think", "Write", "Speak")

// --- Rules ------------------------------------------------------------------
//
// Three rules carry the notebook motif, separated by weight and colour rather
// than by dash pattern:
//   stroke-ruled     the handwriting guides a student writes on
//   stroke-hairline  the quiet border of a callout panel
//   stroke-margin    the rust spine
// Every rule in the system is solid. An earlier draft of this file described a
// solid/dashed grammar for "write here" versus "fill this in"; no dashed stroke
// was ever built, so the grammar is not claimed here.

#let ruled = rgb("#c6d0c8") // handwriting guides; dark enough for a home laser
#let stroke-ruled = 0.2mm + ruled
#let stroke-hairline = 0.25mm + line-soft
#let stroke-margin = 0.25mm + coral-deep

// --- Typefaces --------------------------------------------------------------
//
// The two brand faces, both OFL, both Korean-capable, both vendored in
// workbooks/assets/fonts so builds are reproducible on any machine.
//
// Gowun Batang has exactly two weights, regular and bold. Nothing may ask for
// another: Typst would synthesise it and the result does not match the logo.

#let serif = "Gowun Batang" // display and reading text, English and Korean
#let sans = "IBM Plex Sans KR" // labels, furniture, instructions

// --- Type scale -------------------------------------------------------------

#let size-cover-title = 44pt
#let size-cover-series = 8.5pt
#let size-lesson-title = 24pt
#let size-section-title = 15pt
#let size-body = 11pt // prompts — the reading size of the workbook
#let size-quote = 10pt
#let size-vocab-term = 12.5pt
#let size-vocab-body = 9.5pt
#let size-label = 7.5pt
#let size-furniture = 8pt

#let tracking-caps = 0.1em

// --- Page geometry ----------------------------------------------------------
//
// A4, and symmetric across every page: the layout never depends on whether a
// sheet is printed left- or right-hand, because students print these themselves,
// often single-sided.
//
// A rust spine sits at 24 mm; content starts 5 mm to its right. Question numbers
// hang on the outside of the spine, leaving the reading measure uninterrupted.

#let paper-size = "a4"
#let page-width = 210mm
#let page-height = 297mm

#let margin-top = 20mm
#let margin-bottom = 18mm
#let margin-left = 29mm
#let margin-right = 24mm

#let head-ascent = 3.5mm
#let foot-descent = 1mm

#let block-width = page-width - margin-left - margin-right
#let body-height = page-height - margin-top - margin-bottom

// The margin rule, and the gutter left of it where question numbers sit.
#let rule-x = 24mm
#let gutter-width = 8mm
#let gutter-dx = -15mm // from the text block's left edge

// --- Section tabs -----------------------------------------------------------
//
// Four index tabs down the outer edge, the current one saturated and extended.
// Lifted from the site's own `.step-tabs`, where the same four colours are the
// same four steps. They are a section finder when flipping and a progress
// indicator when reading, and they cost nothing to print.
//
// They do not bleed. A home printer cannot print to the edge, and a tab clipped
// by an unprintable margin looks broken rather than deliberate.
//
// All four share an outer edge at `tab-right`, and the active tab extends
// *inward* rather than outward. Two reasons, and the first is not cosmetic:
//
//   - A common home laser or inkjet cannot print within about 4.2-5 mm of the
//     sheet edge. An outward-extending active tab put the current section — the
//     one marker that has to survive — inside that band, so the "you are here"
//     signal was the first thing a home printer clipped. `tab-right` keeps
//     every tab 8 mm clear of the edge.
//   - A stack of index tabs reads as a stack because its outer edge is flush.
//     Ragged outer edges read as four unrelated swatches.

#let tab-right = 202mm // 8mm of clearance; safe on a home printer
#let tab-width = 11mm
#let tab-width-active = 15mm
#let tab-height = 8.5mm
#let tab-gap = 2mm
#let tab-top = 22mm
#let tab-radius = 2.5pt

// --- Vertical rhythm --------------------------------------------------------

#let leading-body = 0.75em
#let space-between-questions = 6mm
#let space-prompt-to-response = 1mm
#let space-band-above = 9mm
#let space-band-below = 9mm
#let section-band-min-height = 23.5mm
#let space-vocab-field = 2.4mm
#let space-vocab-entry = 4.5mm

// --- Handwriting response areas ---------------------------------------------
//
// 7mm keeps handwriting comfortable while allowing full-page response surfaces
// to use the page efficiently. Keep this as the single source of truth.

#let line-gap = 7mm

// Named response sizes, in ruled lines.
#let lines-short = 3
#let lines-medium = 4
#let lines-extended = 6

// Tutor-facing response-space presets. The extended-answer mapping is
// provisional until the final page design is approved; lesson content stores
// the semantic preset rather than this derived number.
#let response-short-answer-lines = 3
#let response-short-paragraph-lines = 6
#let response-extended-answer-lines = 12

// Exact custom responses longer than this are split onto explicitly labelled
// continuation pages. The first-page cap reserves room for variable prompt and
// guidance content. A dedicated continuation page safely holds up to 35 lines
// at the standard 7mm rhythm.
#let response-first-page-lines = 14
#let response-continuation-max-lines = 35

// --- Cover geometry ---------------------------------------------------------

// Workbook and lesson covers share a full-height, four-band method rail. The
// rest of the sheet is white, matching the interior and reducing ink coverage.
#let cover-rail-width = 24mm
#let cover-content-left = 40mm
#let cover-content-right = 24mm
#let cover-logo-width = 54mm

// --- Assets -----------------------------------------------------------------

// The full brand set, copied from website/public/images/logo/png so the workbook
// and the site cannot drift apart. Re-sync with the script in README.md.
//
// PNG rather than SVG on purpose: the source SVGs set letter-spacing with CSS
// custom properties, which Typst's renderer does not support, so the glyphs
// collapse on top of each other. This was tested, not assumed.
//
// Three shapes, each light and dark:
//   logomark-large  circle, full "4steps BOOK CLUB" lockup
//   logomark-small  circle, compact "4s" — holds up at small sizes
//   logotype        capsule, full lockup, for wide spaces
//
// `-dark` is the reversed form: dark green ground, cream type. It needs a dark
// or coloured ground behind it, so nothing on white should reach for it.

#let logomark-large = "/assets/logo/logomark-large-light.png"
#let logomark-large-dark = "/assets/logo/logomark-large-dark.png"
#let logomark-small = "/assets/logo/logomark-small-light.png"
#let logomark-small-dark = "/assets/logo/logomark-small-dark.png"
#let logotype = "/assets/logo/logotype-light.png"
#let logotype-dark = "/assets/logo/logotype-dark.png"

// The default mark, used on covers. The footer wordmark is typeset from the
// brand faces instead — see `wordmark` in components.typ.
#let logomark = logomark-large

// Height of the coloured bar that opens a section.
#let band-bar-height = 2.5mm
