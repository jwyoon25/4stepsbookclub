# Decap CMS setup

The public announcement pages are generated from Markdown files in
`website/src/content/notices`. Decap CMS writes those files and uploaded media
to the GitHub repository through the private `/admin/` editor.

## One-time deployment setup

The site is hosted on Cloudflare Pages. The Pages project must use the
repository root as its project root so the root-level `functions/` directory is
deployed with the static output.

Use these Cloudflare Pages build settings:

- Build command: `npm run build`
- Build output directory: `website/dist`

Add these production environment variables under Pages → Settings → Variables
and Secrets:

- `GITHUB_OAUTH_ID` — the GitHub OAuth App client ID
- `GITHUB_OAUTH_SECRET` — the GitHub OAuth App client secret, stored as an encrypted secret
- `GITHUB_REPO_PRIVATE` — `0` for the current public repository, or `1` if the repository becomes private

## GitHub OAuth App

Create a GitHub OAuth App under the GitHub account that owns the repository.
Use:

- Application homepage: `https://4stepsbookclub.com`
- Authorization callback URL: `https://4stepsbookclub.com/callback?provider=github`

The founder’s GitHub account must have permission to write to
`jwyoon25/4stepsbookclub`. Decap uses that permission when saving an
announcement or uploading an image.

After adding the Cloudflare variables, trigger a new Pages deployment. The
founder can then open:

`https://4stepsbookclub.com/admin/`

She will log in with GitHub, choose `공지사항`, and create or edit posts using
the title, body, posting date, and optional image fields. Publishing commits
the Markdown and media files to `main`, which triggers the normal Pages build.

## Local development

`npm run build` verifies the Astro content and generated announcement routes.
The OAuth functions are provided by Cloudflare Pages, so the live `/admin/`
login requires a deployed Pages environment with the variables above. The
regular Astro dev server can still be used to preview the public pages.
