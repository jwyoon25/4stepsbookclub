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
// The mark is a sheet of ruled notebook paper: cream ground, soft rules, a rust
// vertical margin rule, the numeral four in butter. The workbook is the thing
// the logo is a picture of, so it does not decorate itself with the logo — it
// reproduces the paper.

#let ink = rgb("#17342f") // forest green; the brand's black
#let ink-soft = rgb("#24483f")
#let ink-body = rgb("#263a34")
#let muted = rgb("#5f7069")
#let faint = rgb("#8a978f") // small labels and quiet furniture

#let paper = rgb("#f7f3ea") // the cream of the mark; covers and tinted panels
#let paper-deep = rgb("#eee7da")
#let canvas = rgb("#fffdf8")

#let coral = rgb("#ef6b4a")
#let coral-deep = rgb("#b84431") // the margin rule
#let line-soft = rgb("#dfe4dc")

// --- Section colours --------------------------------------------------------
//
// The four section colours are the brand's method palette, in method order.
// The sections keep their working names — Comprehension, Analysis, Writing,
// Vocabulary — because that is what is actually on the page; the palette is
// what ties them to READ · THINK · SPEAK · WRITE.
//
// These are pastels. They are fills, never text: every one of them fails
// contrast as type on white. Each has a `-deep` partner for the rare place a
// section has to be named in its own colour.

#let step-fill = (rgb("#f2c55c"), rgb("#9dc5a5"), rgb("#8bc7c3"), rgb("#b9abd8"))
#let step-deep = (rgb("#a4741d"), rgb("#4f7d5b"), rgb("#3a7570"), rgb("#6d5c99"))
#let step-wash = (rgb("#fdf5e2"), rgb("#eef5ef"), rgb("#ebf5f4"), rgb("#f2eef8"))

// --- Rules ------------------------------------------------------------------
//
// Two rule weights carry the notebook motif, and they mean different things:
// solid rules are for writing on, dashed rules are for fields to be filled in.
// The distinction is the mark's own — it alternates solid and dashed — reused
// here as a signal rather than as texture.

#let ruled = rgb("#c6d0c8") // handwriting guides; dark enough for a home laser
#let stroke-ruled = 0.5pt + ruled
#let stroke-hairline = 0.4pt + line-soft
#let stroke-field = (paint: muted.lighten(45%), thickness: 0.5pt, dash: "densely-dashed")
#let stroke-margin = 0.7pt + coral-deep

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

#let size-cover-title = 30pt
#let size-cover-series = 9.5pt
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
// The left margin is wide because the page has a spine. A rust margin rule runs
// the full height at `rule-x`, question numbers hang outside it in the gutter,
// and the text block begins clear of it. This is what makes an unfilled page
// bottom read as paper rather than as a hole — the earlier draft had no vertical
// structure, so every short page looked like a mistake.

#let paper-size = "a4"
#let page-width = 210mm
#let page-height = 297mm

#let margin-top = 20mm
#let margin-bottom = 18mm
#let margin-left = 36mm
#let margin-right = 26mm

#let head-ascent = 9mm
#let foot-descent = 9mm

#let block-width = page-width - margin-left - margin-right
#let body-height = page-height - margin-top - margin-bottom

// The margin rule, and the gutter left of it where question numbers sit.
#let rule-x = 30mm
#let gutter-width = 10mm
#let gutter-dx = -16mm // from the text block's left edge

// --- Section tabs -----------------------------------------------------------
//
// Four index tabs down the outer edge, the current one saturated and extended.
// Lifted from the site's own `.step-tabs`, where the same four colours are the
// same four steps. They are a section finder when flipping and a progress
// indicator when reading, and they cost nothing to print.
//
// They do not bleed. A home printer cannot print to the edge, and a tab clipped
// by an unprintable margin looks broken rather than deliberate.

#let tab-x = 191mm
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
#let space-band-below = 6mm
#let space-vocab-field = 2.4mm
#let space-vocab-entry = 4.5mm

// --- Handwriting response areas ---------------------------------------------
//
// 8.5mm suits a teenage hand. This is the single number most likely to need
// changing after the first real print with real students.

#let line-gap = 8.5mm

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
#let surface-bottom-guard = 4mm

// --- Cover paper ------------------------------------------------------------
//
// Covers reproduce the mark: cream ground, ruled lines edge to edge, rust
// margin rule. Interior pages do not — a full-bleed cream ground is expensive
// on a home printer and greys down pencil. See DESIGN-DECISIONS.md.

#let cover-rule-gap = 9mm
#let cover-rule-top = 24mm

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
