const oauthOrigin = "https://4stepsbookclub.com";
const stateCookieName = "decap_oauth_state";
const allowedAdminOrigins = new Set([oauthOrigin, "https://www.4stepsbookclub.com"]);

function randomHex(bytes = 16) {
  const values = new Uint8Array(bytes);
  crypto.getRandomValues(values);
  return Array.from(values, (value) => value.toString(16).padStart(2, "0")).join("");
}

function readCookie(request, name) {
  const cookieHeader = request.headers.get("Cookie") || "";
  const cookie = cookieHeader
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${name}=`));

  if (!cookie) {
    return "";
  }

  try {
    return decodeURIComponent(cookie.slice(name.length + 1));
  } catch {
    return "";
  }
}

function readStateContext(request) {
  try {
    const context = JSON.parse(readCookie(request, stateCookieName));
    if (
      typeof context.state === "string" &&
      /^[0-9a-f]{32}$/.test(context.state) &&
      allowedAdminOrigins.has(context.adminOrigin)
    ) {
      return context;
    }
  } catch {
    // Invalid or expired state is handled by the caller.
  }

  return null;
}

function serializeJson(value) {
  return JSON.stringify(value).replace(/</g, "\\u003c");
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

function callbackResponse(status, payload, targetOrigin, headers = {}) {
  const nonce = randomHex();
  const message = `authorization:github:${status}:${serializeJson(payload)}`;

  return new Response(
    `<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Authorizing Decap</title></head>
  <body>
    <p>Authorizing Decap...</p>
    <script nonce="${nonce}">
      window.opener && window.opener.postMessage(${serializeJson(message)}, ${serializeJson(targetOrigin)});
      window.close();
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
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        ...headers
      }
    }
  );
}

function logOAuthFailure(request, reason, status) {
  console.error(
    JSON.stringify({
      event: "decap_github_oauth_failure",
      reason,
      status,
      cfRay: request.headers.get("cf-ray") || undefined
    })
  );
}

export async function onRequest({ request, env }) {
  const url = new URL(request.url);

  if (url.searchParams.get("provider") !== "github") {
    return new Response("Invalid provider", { status: 400 });
  }

  if (url.origin !== oauthOrigin) {
    return canonicalRedirect(url);
  }

  const stateContext = readStateContext(request);
  const receivedState = url.searchParams.get("state") || "";
  const targetOrigin = stateContext?.adminOrigin || oauthOrigin;
  const clearStateCookie = `${stateCookieName}=; Max-Age=0; Path=/callback; HttpOnly; Secure; SameSite=Lax`;

  if (!stateContext || !receivedState || stateContext.state !== receivedState) {
    return callbackResponse(
      "error",
      { message: "OAuth state validation failed." },
      targetOrigin,
      { "Set-Cookie": clearStateCookie }
    );
  }

  const providerError = url.searchParams.get("error");
  if (providerError) {
    const message = providerError === "access_denied" ? "GitHub authorization was cancelled." : "GitHub authorization failed.";
    return callbackResponse("error", { message }, targetOrigin, { "Set-Cookie": clearStateCookie });
  }

  if (!env.GITHUB_OAUTH_ID || !env.GITHUB_OAUTH_SECRET) {
    logOAuthFailure(request, "missing_configuration", 500);
    return callbackResponse(
      "error",
      { message: "GitHub OAuth is not configured." },
      targetOrigin,
      { "Set-Cookie": clearStateCookie }
    );
  }

  const code = url.searchParams.get("code");
  if (!code) {
    return callbackResponse(
      "error",
      { message: "GitHub did not return an authorization code." },
      targetOrigin,
      { "Set-Cookie": clearStateCookie }
    );
  }

  let tokenResponse;
  try {
    tokenResponse = await fetch("https://github.com/login/oauth/access_token", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        client_id: env.GITHUB_OAUTH_ID,
        client_secret: env.GITHUB_OAUTH_SECRET,
        code,
        redirect_uri: `${oauthOrigin}/callback?provider=github`,
        grant_type: "authorization_code"
      })
    });
  } catch {
    logOAuthFailure(request, "token_request_failed");
    return callbackResponse(
      "error",
      { message: "GitHub authorization is temporarily unavailable." },
      targetOrigin,
      { "Set-Cookie": clearStateCookie }
    );
  }

  let tokenPayload;
  try {
    tokenPayload = await tokenResponse.json();
  } catch {
    logOAuthFailure(request, "invalid_token_response", tokenResponse.status);
    return callbackResponse(
      "error",
      { message: "GitHub returned an invalid authorization response." },
      targetOrigin,
      { "Set-Cookie": clearStateCookie }
    );
  }

  if (
    !tokenResponse.ok ||
    !tokenPayload ||
    typeof tokenPayload !== "object" ||
    typeof tokenPayload.access_token !== "string" ||
    !tokenPayload.access_token
  ) {
    logOAuthFailure(request, "token_exchange_rejected", tokenResponse.status);
    const message =
      tokenPayload && typeof tokenPayload === "object" && typeof tokenPayload.error_description === "string"
        ? tokenPayload.error_description
        : "GitHub authorization failed.";
    return callbackResponse("error", { message }, targetOrigin, { "Set-Cookie": clearStateCookie });
  }

  return callbackResponse(
    "success",
    { token: tokenPayload.access_token },
    targetOrigin,
    { "Set-Cookie": clearStateCookie }
  );
}
