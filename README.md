# 4steps Bookclub

This repository contains the 4steps Bookclub website and the internal
workbook publishing system.

## Projects

- `website/` — the Astro-powered customer-facing website.
- `workbooks/` — the Typst-based workbook generation scaffold.

The website includes a Decap CMS announcement editor. One-time Cloudflare and
GitHub OAuth setup is documented in [website/DECAP_SETUP.md](website/DECAP_SETUP.md).

## Publishing an announcement

1. Open [4stepsbookclub.com/admin](https://4stepsbookclub.com/admin/).
2. Log in with an authorized GitHub account. Allow pop-ups if prompted.
3. Select **공지사항** and create a new announcement.
4. Enter the title, date, and content. You may add up to five images, with a
   maximum size of 2 MB per image.
5. Click **게시** to publish.

GitHub stores the post and Cloudflare publishes it automatically, usually
within a few minutes. To edit or delete a post, open it again in the admin
page and publish the change. The `#/` added to the admin URL is Decap's normal
browser-side routing and can be ignored.

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
