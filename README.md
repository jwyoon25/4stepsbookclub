# 4steps Bookclub

The 4steps Bookclub repository contains the public Astro website, its Decap
CMS announcement editor, and the initial Typst-based workbook publishing
system.

The live site is [4stepsbookclub.com](https://4stepsbookclub.com).

## Repository layout

```text
.
├── functions/       # Cloudflare Pages Functions for GitHub OAuth
├── tests/            # OAuth and admin media-guard tests
├── website/          # Astro site, content, assets, and Decap CMS admin
└── workbooks/        # Typst workbook publishing scaffold
```

Announcements are stored as Markdown in
`website/src/content/notices`. Images uploaded through the CMS are stored in
`website/public/images/notices`.

## Requirements

- Node.js and npm
- [Typst](https://typst.app/) only if you are working on the workbook system

Install the Node dependencies from the repository root:

```bash
npm install
```

To install Typst on macOS with Homebrew:

```bash
brew install typst
```

## Website development

Run the Astro development server:

```bash
npm run dev
```

The public site is available at `http://localhost:4321`. The useful website
commands are:

```bash
npm run build       # Build the static site into website/dist/
npm run preview     # Preview the latest production build
npm test            # Run the repository test suite
```

The local Astro server previews the public pages. Decap CMS login and GitHub
OAuth are provided by Cloudflare Pages Functions, so a working `/admin/`
login requires a deployed Pages environment and its OAuth variables. See
[website/DECAP_SETUP.md](website/DECAP_SETUP.md) for the one-time Cloudflare
Pages and GitHub OAuth setup.

## Publishing an announcement

1. Open [4stepsbookclub.com/admin](https://4stepsbookclub.com/admin/).
2. Sign in with an authorized GitHub account. Allow pop-ups if prompted.
3. Select **공지사항** and create or edit an announcement.
4. Enter the title, posting date, and content. You may add up to five images;
   each image must be no larger than 2 MB.
5. Click **게시** to publish.

Decap commits the Markdown and media files to GitHub, and Cloudflare rebuilds
the site automatically. Changes usually appear within a few minutes. The
`#/` fragment that Decap adds to the admin URL is expected.

## Workbook system

The workbook design system is implemented in Typst and proven by a nine-page
specimen. A versioned JSON content model, package validator, and data-driven PDF
renderer are implemented; the staff editor is the remaining layer.

```bash
npm run workbook:specimen        # build the design specimen
npm run workbook:specimen:watch
npm run workbook:validate        # validate the example content package
npm run workbook:render          # render all example student/teacher PDFs
npm run workbook:build           # build the compilation smoke test
npm run workbook:watch
```

Render a production content package by passing its manifest path after `--`:

```bash
npm run workbook:render -- workbooks/content/the-book-id/workbook.json
```

The renderer creates a complete workbook PDF and one standalone PDF per lesson,
in both student and teacher editions.

`workbook:specimen` writes `workbooks/output/specimen.pdf`, the file to look at
when changing anything in `workbooks/system/`. Generated PDFs in that directory
are ignored by Git.

The two brand typefaces are vendored in `workbooks/assets/fonts`, so every build
must pass `--font-path`; the npm scripts already do. See
[workbooks/README.md](workbooks/README.md) for the project structure and
[workbooks/DESIGN-DECISIONS.md](workbooks/DESIGN-DECISIONS.md) for the design
reasoning.

## Deployment checklist

Before deploying, run:

```bash
npm test
npm run build
```

The Cloudflare Pages project should use the repository root as its project
root, with `npm run build` as the build command and `website/dist` as the
output directory. The root project configuration is intentional: it lets
Cloudflare deploy the `functions/` directory alongside the generated site.
