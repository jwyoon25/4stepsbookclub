const oauthOrigin = "https://4stepsbookclub.com";
const stateCookieName = "decap_oauth_state";
const allowedAdminOrigins = new Map([
  ["4stepsbookclub.com", oauthOrigin],
  ["www.4stepsbookclub.com", "https://www.4stepsbookclub.com"]
]);

function randomHex(bytes = 16) {
  const values = new Uint8Array(bytes);
  crypto.getRandomValues(values);
  return Array.from(values, (value) => value.toString(16).padStart(2, "0")).join("");
}

function serializeJson(value) {
  return JSON.stringify(value).replace(/</g, "\\u003c");
}

function resolveAdminOrigin(url) {
  const siteId = (url.searchParams.get("site_id") || "4stepsbookclub.com").toLowerCase();
  return allowedAdminOrigins.get(siteId) || "";
}

function canonicalRedirect(url) {
  const canonicalUrl = new URL(`${url.pathname}${url.search}`, oauthOrigin);
  return new Response(null, {
    status: 307,
    headers: {
      "Cache-Control": "no-store",
      Location: canonicalUrl.toString(),
      "Referrer-Policy": "no-referrer"
    }
  });
}

function handshakeResponse({ authorizationUrl, adminOrigin, stateCookie }) {
  const nonce = randomHex();
  const safeAuthorizationUrl = serializeJson(authorizationUrl);
  const safeAdminOrigin = serializeJson(adminOrigin);

  return new Response(
    `<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Authorizing GitHub</title></head>
  <body>
    <p id="status">Connecting to GitHub...</p>
    <script nonce="${nonce}">
      const authorizationUrl = ${safeAuthorizationUrl};
      const adminOrigin = ${safeAdminOrigin};
      let redirectStarted = false;

      const redirectToGitHub = () => {
        if (redirectStarted) return;
        redirectStarted = true;
        window.location.replace(authorizationUrl);
      };

      if (window.opener) {
        window.addEventListener("message", (event) => {
          if (event.origin === adminOrigin && event.data === "authorizing:github") {
            redirectToGitHub();
          }
        });

        window.opener.postMessage("authorizing:github", adminOrigin);
        window.setTimeout(redirectToGitHub, 500);
      } else {
        document.querySelector("#status").textContent =
          "The sign-in window was disconnected. Close it and try again with pop-ups allowed.";
      }
    </script>
  </body>
</html>`,
    {
      headers: {
        "Cache-Control": "no-store",
        "Content-Security-Policy": `default-src 'none'; script-src 'nonce-${nonce}'; base-uri 'none'; frame-ancestors 'none'`,
        "Content-Type": "text/html; charset=utf-8",
        "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
        "Referrer-Policy": "no-referrer",
        "Set-Cookie": stateCookie,
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY"
      }
    }
  );
}

export function onRequest({ request, env }) {
  const url = new URL(request.url);

  if (url.searchParams.get("provider") !== "github") {
    return new Response("Invalid provider", { status: 400 });
  }

  const adminOrigin = resolveAdminOrigin(url);
  if (!adminOrigin) {
    return new Response("Invalid site", { status: 400 });
  }

  if (url.origin !== oauthOrigin) {
    return canonicalRedirect(url);
  }

  if (!env.GITHUB_OAUTH_ID || !env.GITHUB_OAUTH_SECRET) {
    return new Response("GitHub OAuth is not configured", { status: 500 });
  }

  const state = randomHex();
  const callbackUrl = `${oauthOrigin}/callback?provider=github`;
  const scope = env.GITHUB_REPO_PUBLIC === "1" ? "public_repo" : "repo";
  const authorizationUrl = new URL("https://github.com/login/oauth/authorize");

  authorizationUrl.search = new URLSearchParams({
    client_id: env.GITHUB_OAUTH_ID,
    redirect_uri: callbackUrl,
    scope,
    state
  });

  const cookieValue = encodeURIComponent(JSON.stringify({ state, adminOrigin }));
  return handshakeResponse({
    authorizationUrl: authorizationUrl.toString(),
    adminOrigin,
    stateCookie: `${stateCookieName}=${cookieValue}; Max-Age=600; Path=/callback; HttpOnly; Secure; SameSite=Lax`
  });
}
