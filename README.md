# 4steps Bookclub

This repository contains the 4steps Bookclub website and the internal
workbook publishing system.

## Projects

- `website/` — the Astro-powered customer-facing website.
- `workbooks/` — the Typst-based workbook generation scaffold.

The website includes a Decap CMS announcement editor. One-time Cloudflare and
GitHub OAuth setup is documented in [website/DECAP_SETUP.md](website/DECAP_SETUP.md).

The root package provides convenient commands for both projects while keeping
their source files and build systems separate.

## Common commands

```bash
npm run dev
npm run build
npm run workbook:build
```

For project-specific commands, see [website/package.json](website/package.json)
and [workbooks/README.md](workbooks/README.md).
