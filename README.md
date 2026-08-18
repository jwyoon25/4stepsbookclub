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

The workbook project is currently infrastructure scaffolding. Its Typst smoke
test can be built or watched from the repository root:

```bash
npm run workbook:build
npm run workbook:watch
```

The build writes
`workbooks/output/workbook-smoke-test.pdf`. Generated PDFs in that directory
are ignored by Git. See [workbooks/README.md](workbooks/README.md) for the
project structure and Typst guidance.

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
