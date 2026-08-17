const stateCookieName = "decap_oauth_state";

function randomHex(bytes = 16) {
  const values = new Uint8Array(bytes);
  crypto.getRandomValues(values);
  return Array.from(values, (value) => value.toString(16).padStart(2, "0")).join("");
}

function serializeJson(value) {
  return JSON.stringify(value).replace(/</g, "\\u003c");
}

function handshakeResponse({ authorizationUrl, origin, stateCookie }) {
  const safeAuthorizationUrl = serializeJson(authorizationUrl);
  const safeOrigin = serializeJson(origin);

  return new Response(
    `<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Authorizing GitHub</title></head>
  <body>
    <p>Connecting to GitHub...</p>
    <script>
      const authorizationUrl = ${safeAuthorizationUrl};
      const origin = ${safeOrigin};

      window.addEventListener("message", (event) => {
        if (event.source === window.opener && event.origin === origin && event.data === "authorizing:github") {
          window.location.replace(authorizationUrl);
        }
      });

      if (window.opener) {
        window.opener.postMessage("authorizing:github", origin);
      }
    </script>
  </body>
</html>`,
    {
      headers: {
        "Cache-Control": "no-store",
        "Content-Type": "text/html; charset=utf-8",
        "Set-Cookie": stateCookie
      }
    }
  );
}

export function onRequest({ request, env }) {
  const url = new URL(request.url);

  if (url.searchParams.get("provider") !== "github") {
    return new Response("Invalid provider", { status: 400 });
  }

  if (!env.GITHUB_OAUTH_ID) {
    return new Response("GitHub OAuth is not configured", { status: 500 });
  }

  const state = randomHex();
  const callbackUrl = `${url.origin}/callback?provider=github`;
  const scope = env.GITHUB_REPO_PRIVATE === "1" ? "repo,user" : "public_repo,user";
  const authorizationUrl = new URL("https://github.com/login/oauth/authorize");

  authorizationUrl.search = new URLSearchParams({
    client_id: env.GITHUB_OAUTH_ID,
    redirect_uri: callbackUrl,
    scope,
    state
  });

  return handshakeResponse({
    authorizationUrl: authorizationUrl.toString(),
    origin: url.origin,
    stateCookie: `${stateCookieName}=${state}; Max-Age=600; Path=/callback; HttpOnly; Secure; SameSite=Lax`
  });
}
