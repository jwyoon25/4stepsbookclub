# 4steps Book Club — Brand Direction

## Creative idea

**A contemporary reading room.**

The identity should feel warm, thoughtful, and academically credible without looking like a conventional cram-school website. Editorial typography, paper-like backgrounds, notebook details, and confident color blocks make the learning process tangible for parents browsing on a phone.

The central brand line is:

> 읽은 책이, 아이의 문장이 되도록.

The visual and verbal sequence is:

> READ → THINK → SPEAK → WRITE

## Logo

**Concept: Four lines. One method.**

The identity turns the four stages of the program into ruled lines on a reading-and-writing page. The numeral `4` is drawn directly through those rules, while the coral fourth line becomes its crossbar. The result connects the name, the four-part method, and the act of writing in one academically grounded mark.

The editorial serif wordmark keeps the identity warm and publication-like. A restrained rounded-rectangle border gives each logotype the feeling of a considered bookplate instead of a generic app badge.

- Primary dark logotype: `public/images/logo/logotype-dark.svg`
- Primary light logotype: `public/images/logo/logotype-light.svg`
- Compact dark `4s` logomark: `public/images/logo/logomark-small-dark.svg`
- Compact light `4s` logomark: `public/images/logo/logomark-small-light.svg`
- Large dark complete logomark: `public/images/logo/logomark-large-dark.svg`
- Large light complete logomark: `public/images/logo/logomark-large-light.svg`
- High-resolution PNG exports: `public/images/logo/png/`
- Generated browser and device icons: `public/images/icons/`
- Every logotype ends at its rounded-rectangle border; the area outside the border is always transparent.
- Light variants use Warm Paper inside their border. Dark variants use Library Green inside their border.
- Compact marks use the same construction as a circle rather than a rectangular badge.
- Keep clear space around a lockup equal to roughly one ruled-line interval.
- Use the light lockup on Warm Paper and pale surfaces; use the dark lockup when a stronger brand anchor is needed.
- Library Green carries the identity. Coral is reserved for the active writing line and the crossbar of the `4`.
- Use the compact mark when the full wordmark would render below 120px wide.

## Color palette

| Role | Name | Hex |
| --- | --- | --- |
| Primary | Library Green | `#17342F` |
| Primary soft | Reading Green | `#24483F` |
| Background | Warm Paper | `#F7F3EA` |
| Background light | Canvas | `#FFFDF8` |
| Action | Teacher Coral | `#EF6B4A` |
| Action dark | Markup Coral | `#C84F37` |
| Accent | Pencil Yellow | `#F2C55C` |
| Step accent | Quiet Aqua | `#8BC7C3` |
| Step accent | Soft Sage | `#9DC5A5` |
| Step accent | Margin Lilac | `#B9ABD8` |
| Body text | Deep Graphite | `#263A34` |
| Secondary text | Muted Green Gray | `#66766F` |

Library Green and Warm Paper should carry most of the experience. Coral is reserved for decisions, annotations, and conversion moments. Yellow, aqua, sage, and lilac support the four-step story and should not compete with calls to action.

Third-party platform marks use the original Naver Blog, KakaoTalk Channel, and Instagram artwork without recoloring or redrawing. Keep them visually subordinate to the 4steps identity and pair icon-only header links with accessible channel labels.

## Typography

- **Display and editorial headlines:** `Gowun Batang`, 700
- **Body, navigation, forms, and metadata:** `IBM Plex Sans KR`, 400–700
- Use the serif for ideas and emotional emphasis, not for dense interface copy.
- Primary Korean body copy is 16px with generous line height. The 14px compact-body role is reserved for supporting card copy and dense utility content.
- Keep headings short enough to scan in two to four lines at 360–430px.

### Type roles

The site uses a deliberately small semantic system. New content should choose one of these roles and should not introduce another font size or weight without a deliberate design reason.

| Role | Token | Family / weight | Use |
| --- | --- | --- | --- |
| Hero | `--type-hero` | Gowun Batang 700 | The single largest headline on the page |
| Section | `--type-section` | Gowun Batang 700 | Section headings and feature statements |
| Heading | `--type-heading` | Gowun Batang 700 | Card, panel, and subsection headings |
| Body | `--type-body` | IBM Plex Sans KR 400–600 | Primary paragraphs and controls |
| Small | `--type-small` | IBM Plex Sans KR 400–600 | Supporting card copy and dense content |
| Label | `--type-label` | IBM Plex Sans KR 400–700 | Buttons, navigation, captions, tags, and utility information |

Only the loaded weights 400, 600, and 700 should be used. Line-height and tracking follow the shared `--leading-*` and `--tracking-*` tokens in `src/pages/index.astro`.

## Art direction

- Prefer real workbook and feedback pages over generic stock photography.
- Use notebook lines, page tabs, annotations, and paper cards as supporting motifs.
- Favor asymmetrical editorial composition over centered corporate feature grids.
- Rounded forms should feel like paper, tabs, and speech notes rather than generic app UI.
- Avoid crest-led branding and overused “elite education” imagery. University marks may appear only in approved, clearly contextualized credential callouts—not as the 4steps identity or an implied university partnership.

## Voice

- Korean-first, concise, calm, and specific.
- Show the learning process instead of promising outcomes.
- Write to a parent who wants to understand what happens in class.
- Avoid exaggerated superlatives and unverified curriculum, policy, or performance claims.

## Mobile rules

- Design and QA first at 390px, then verify 320px and 430px.
- Keep primary tap targets at least 44px high.
- Present dense work samples through selectable thumbnails and a zoomable modal.
- Use only one fixed conversion control, reveal it after the hero, and hide it near the consultation form and footer.
- Preserve a clear scroll journey: offer → method → evidence → trust → placement → questions → consultation.
- FAQ and Notices must remain directly reachable from the mobile menu.
