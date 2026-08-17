# Open Graph cover

`og-default.html` is the source for the site's link preview card. The published
asset lives at `public/images/og/og-default.png` (1200×630) and is referenced by
the `og:image` and `twitter:image` tags in `src/pages/index.astro`.

The layout is drawn with the same tokens as the site — Warm Paper ground, the
`logotype-light.svg` bookplate, the hero line with its coral `문장` marker, and
the four step tabs in Pencil Yellow, Soft Sage, Quiet Aqua, and Margin Lilac.
The Library Green method band keeps the learning sequence legible at small
social-preview sizes and gives the card a stronger branded edge.
Fonts load from Google Fonts, so rendering needs a network connection.

## Regenerating the PNG

From this directory:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --hide-scrollbars --allow-file-access-from-files --window-size=1200,630 --virtual-time-budget=25000 --screenshot="../../public/images/og/og-default.png" "file://$PWD/og-default.html"
```

`--virtual-time-budget` has to stay generous: Gowun Batang ships Korean as many
subset files, and a short budget screenshots the page before they arrive and
silently falls back to a system sans.

## When to regenerate

Regenerate after any change to the brand line, the logotype, or the palette so
the card keeps matching the hero. Keep the output at exactly 1200×630 — the
dimensions are declared in `og:image:width` / `og:image:height`, and platforms
trust those tags over the file.
