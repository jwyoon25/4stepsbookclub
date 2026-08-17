# Decap CMS setup

The public announcement pages are generated from Markdown files in
`website/src/content/notices`. Decap CMS writes those files and uploaded media
to the GitHub repository through the private `/admin/` editor.

The admin page pins Decap CMS 3.15.1 and verifies the downloaded entry bundle
with a SHA-384 Subresource Integrity hash. When updating Decap, update the
version and integrity hash together and verify the OAuth handshake tests still
pass.

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

The OAuth Functions accept Decap login requests only for these admin origins:

- `https://4stepsbookclub.com`
- `https://www.4stepsbookclub.com`

If the production domain changes, update the allowlists in both
`functions/auth.js` and `functions/callback.js`, the Decap `base_url`, and the
GitHub OAuth App settings together. Do not add preview or user-controlled
domains to the allowlist.

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

OAuth transport, configuration, and GitHub token-exchange failures emit a
structured `decap_github_oauth_failure` event in Cloudflare logs. These events
contain only a failure category, HTTP status, and Cloudflare Ray ID; OAuth
codes, state values, access tokens, and client secrets must never be logged.

## Verification

Run before deployment:

```sh
npm test
npm run build
```

The tests cover the Decap handshake, apex and `www` origins, state cookies,
public/private scopes, callback target origins, cancellation, malformed GitHub
responses, and token-exchange network failures. After deployment, verify a
real GitHub login from both supported `/admin/` origins.

## Local development

`npm run build` verifies the Astro content and generated announcement routes.
The OAuth functions are provided by Cloudflare Pages, so the live `/admin/`
login requires a deployed Pages environment with the variables above. The
regular Astro dev server can still be used to preview the public pages.
