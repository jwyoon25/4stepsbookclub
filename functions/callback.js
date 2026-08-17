const stateCookieName = "decap_oauth_state";

function readCookie(request, name) {
  const cookieHeader = request.headers.get("Cookie") || "";
  const cookie = cookieHeader
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${name}=`));

  return cookie ? decodeURIComponent(cookie.slice(name.length + 1)) : "";
}

function serializeJson(value) {
  return JSON.stringify(value).replace(/</g, "\\u003c");
}

function callbackResponse(status, payload, headers = {}) {
  const message = `authorization:github:${status}:${serializeJson(payload)}`;

  return new Response(
    `<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Authorizing Decap</title></head>
  <body>
    <p>Authorizing Decap...</p>
    <script>
      window.opener && window.opener.postMessage(${serializeJson(message)}, "*");
      window.close();
    </script>
  </body>
</html>`,
    {
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        ...headers
      }
    }
  );
}

export async function onRequest({ request, env }) {
  const url = new URL(request.url);

  if (url.searchParams.get("provider") !== "github") {
    return new Response("Invalid provider", { status: 400 });
  }

  const expectedState = readCookie(request, stateCookieName);
  const receivedState = url.searchParams.get("state") || "";
  const clearStateCookie = `${stateCookieName}=; Max-Age=0; Path=/callback; HttpOnly; Secure; SameSite=Lax`;

  if (!expectedState || !receivedState || expectedState !== receivedState) {
    return callbackResponse("error", { message: "OAuth state validation failed." }, { "Set-Cookie": clearStateCookie });
  }

  const code = url.searchParams.get("code");
  if (!code || !env.GITHUB_OAUTH_ID || !env.GITHUB_OAUTH_SECRET) {
    return callbackResponse("error", { message: "GitHub OAuth is not configured." }, { "Set-Cookie": clearStateCookie });
  }

  const tokenResponse = await fetch("https://github.com/login/oauth/access_token", {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      client_id: env.GITHUB_OAUTH_ID,
      client_secret: env.GITHUB_OAUTH_SECRET,
      code,
      redirect_uri: `${url.origin}/callback?provider=github`,
      grant_type: "authorization_code"
    })
  });

  const tokenPayload = await tokenResponse.json();
  if (!tokenResponse.ok || !tokenPayload.access_token) {
    return callbackResponse(
      "error",
      { message: tokenPayload.error_description || "GitHub authorization failed." },
      { "Set-Cookie": clearStateCookie }
    );
  }

  return callbackResponse("success", { token: tokenPayload.access_token }, { "Set-Cookie": clearStateCookie });
}
