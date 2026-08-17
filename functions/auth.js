const stateCookieName = "decap_oauth_state";

function randomHex(bytes = 16) {
  const values = new Uint8Array(bytes);
  crypto.getRandomValues(values);
  return Array.from(values, (value) => value.toString(16).padStart(2, "0")).join("");
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

  return new Response(null, {
    status: 302,
    headers: {
      Location: authorizationUrl.toString(),
      "Set-Cookie": `${stateCookieName}=${state}; Max-Age=600; Path=/callback; HttpOnly; Secure; SameSite=Lax`
    }
  });
}
