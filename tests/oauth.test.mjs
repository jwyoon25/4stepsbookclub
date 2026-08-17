import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const rootUrl = new URL("../", import.meta.url);

async function loadModule(path) {
  const source = await readFile(new URL(path, rootUrl), "utf8");
  return import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
}

const { onRequest: authorize } = await loadModule("functions/auth.js");
const { onRequest: callback } = await loadModule("functions/callback.js");

const configuredEnv = {
  GITHUB_OAUTH_ID: "test-client-id",
  GITHUB_OAUTH_SECRET: "test-client-secret",
  GITHUB_REPO_PRIVATE: "0"
};

function scriptLiteral(html, name) {
  const match = html.match(new RegExp(`const ${name} = ("(?:[^"\\\\]|\\\\.)*");`));
  assert.ok(match, `Expected ${name} in response HTML`);
  return JSON.parse(match[1]);
}

function stateFromResponse(response) {
  const cookie = response.headers.get("set-cookie");
  assert.ok(cookie);
  const value = cookie.match(/^decap_oauth_state=([^;]+)/)?.[1];
  assert.ok(value);
  return JSON.parse(decodeURIComponent(value));
}

function callbackRequest({ stateContext, query, origin = "https://4stepsbookclub.com" }) {
  const cookieValue = encodeURIComponent(JSON.stringify(stateContext));
  return new Request(`${origin}/callback?provider=github&state=${stateContext.state}${query}`, {
    headers: { Cookie: `decap_oauth_state=${cookieValue}` }
  });
}

test("admin CSP permits Decap 3.15.1 configuration evaluation only on admin routes", async () => {
  const headers = await readFile(new URL("website/public/_headers", rootUrl), "utf8");
  const adminPolicy = headers.match(/^\/admin\/\*\n  Content-Security-Policy: (.+)$/m)?.[1];

  assert.ok(adminPolicy, "Expected an admin Content-Security-Policy");
  assert.match(adminPolicy, /script-src 'self' 'unsafe-eval' https:\/\/unpkg\.com/);
  assert.equal(headers.match(/'unsafe-eval'/g)?.length, 1);
});

test("authorization handshake is origin-bound and uses minimal public scope", async () => {
  const response = await authorize({
    request: new Request(
      "https://4stepsbookclub.com/auth?provider=github&site_id=www.4stepsbookclub.com&scope=repo"
    ),
    env: configuredEnv
  });
  const html = await response.text();
  const authorizationUrl = new URL(scriptLiteral(html, "authorizationUrl"));
  const stateContext = stateFromResponse(response);

  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.match(response.headers.get("content-security-policy"), /script-src 'nonce-[0-9a-f]{32}'/);
  assert.equal(scriptLiteral(html, "adminOrigin"), "https://www.4stepsbookclub.com");
  assert.ok(html.includes("event.source === window.opener"));
  assert.ok(html.includes("event.origin === adminOrigin"));
  assert.equal(stateContext.adminOrigin, "https://www.4stepsbookclub.com");
  assert.match(stateContext.state, /^[0-9a-f]{32}$/);
  assert.equal(authorizationUrl.searchParams.get("state"), stateContext.state);
  assert.equal(authorizationUrl.searchParams.get("scope"), "public_repo");
  assert.equal(
    authorizationUrl.searchParams.get("redirect_uri"),
    "https://4stepsbookclub.com/callback?provider=github"
  );
});

test("authorization validates configuration, sites, canonical host, and private scope", async () => {
  const missingSecret = await authorize({
    request: new Request("https://4stepsbookclub.com/auth?provider=github"),
    env: { GITHUB_OAUTH_ID: "test-client-id" }
  });
  assert.equal(missingSecret.status, 500);

  const invalidSite = await authorize({
    request: new Request("https://4stepsbookclub.com/auth?provider=github&site_id=attacker.example"),
    env: configuredEnv
  });
  assert.equal(invalidSite.status, 400);

  const redirect = await authorize({
    request: new Request("https://www.4stepsbookclub.com/auth?provider=github&site_id=www.4stepsbookclub.com"),
    env: configuredEnv
  });
  assert.equal(redirect.status, 307);
  assert.equal(
    redirect.headers.get("location"),
    "https://4stepsbookclub.com/auth?provider=github&site_id=www.4stepsbookclub.com"
  );

  const privateResponse = await authorize({
    request: new Request("https://4stepsbookclub.com/auth?provider=github"),
    env: { ...configuredEnv, GITHUB_REPO_PRIVATE: "1" }
  });
  const privateUrl = new URL(scriptLiteral(await privateResponse.text(), "authorizationUrl"));
  assert.equal(privateUrl.searchParams.get("scope"), "repo");

  const defaultPrivateResponse = await authorize({
    request: new Request("https://4stepsbookclub.com/auth?provider=github"),
    env: {
      GITHUB_OAUTH_ID: configuredEnv.GITHUB_OAUTH_ID,
      GITHUB_OAUTH_SECRET: configuredEnv.GITHUB_OAUTH_SECRET
    }
  });
  const defaultPrivateUrl = new URL(scriptLiteral(await defaultPrivateResponse.text(), "authorizationUrl"));
  assert.equal(defaultPrivateUrl.searchParams.get("scope"), "repo");
});

test("successful callback sends only the token to the state-bound exact origin", async () => {
  const stateContext = {
    state: "a".repeat(32),
    adminOrigin: "https://www.4stepsbookclub.com"
  };
  let exchangeBody;
  const originalFetch = globalThis.fetch;

  try {
    globalThis.fetch = async (_url, options) => {
      exchangeBody = JSON.parse(options.body);
      return Response.json({ access_token: "test-access-token" });
    };

    const response = await callback({
      request: callbackRequest({ stateContext, query: "&code=test-code" }),
      env: configuredEnv
    });
    const html = await response.text();

    assert.equal(response.headers.get("cache-control"), "no-store");
    assert.ok(html.includes("authorization:github:success:"));
    assert.ok(html.includes("test-access-token"));
    assert.ok(html.includes('"https://www.4stepsbookclub.com"'));
    assert.ok(!html.includes('"*"'));
    assert.ok(!html.includes("test-client-secret"));
    assert.deepEqual(exchangeBody, {
      client_id: "test-client-id",
      client_secret: "test-client-secret",
      code: "test-code",
      redirect_uri: "https://4stepsbookclub.com/callback?provider=github",
      grant_type: "authorization_code"
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("callback handles cancellation, invalid state, and missing code", async () => {
  const stateContext = {
    state: "b".repeat(32),
    adminOrigin: "https://4stepsbookclub.com"
  };

  const cancelled = await callback({
    request: callbackRequest({ stateContext, query: "&error=access_denied" }),
    env: configuredEnv
  });
  assert.ok((await cancelled.text()).includes("GitHub authorization was cancelled."));

  const invalidState = await callback({
    request: new Request("https://4stepsbookclub.com/callback?provider=github&state=invalid"),
    env: configuredEnv
  });
  assert.ok((await invalidState.text()).includes("OAuth state validation failed."));

  const missingCode = await callback({
    request: callbackRequest({ stateContext, query: "" }),
    env: configuredEnv
  });
  assert.ok((await missingCode.text()).includes("GitHub did not return an authorization code."));
});

test("callback converts GitHub transport and response failures to Decap errors", async () => {
  const stateContext = {
    state: "c".repeat(32),
    adminOrigin: "https://4stepsbookclub.com"
  };
  const originalFetch = globalThis.fetch;
  const originalConsoleError = console.error;

  try {
    console.error = () => {};
    globalThis.fetch = async () => {
      throw new Error("network unavailable");
    };
    const networkFailure = await callback({
      request: callbackRequest({ stateContext, query: "&code=test-code" }),
      env: configuredEnv
    });
    assert.ok((await networkFailure.text()).includes("temporarily unavailable"));

    globalThis.fetch = async () => new Response("bad gateway", { status: 502 });
    const invalidJson = await callback({
      request: callbackRequest({ stateContext, query: "&code=test-code" }),
      env: configuredEnv
    });
    assert.ok((await invalidJson.text()).includes("invalid authorization response"));

    globalThis.fetch = async () => Response.json(null, { status: 502 });
    const emptyJson = await callback({
      request: callbackRequest({ stateContext, query: "&code=test-code" }),
      env: configuredEnv
    });
    assert.ok((await emptyJson.text()).includes("GitHub authorization failed."));

    globalThis.fetch = async () =>
      Response.json(
        { error_description: "</script><script>globalThis.compromised=true</script>" },
        { status: 400 }
      );
    const rejected = await callback({
      request: callbackRequest({ stateContext, query: "&code=test-code" }),
      env: configuredEnv
    });
    const rejectedHtml = await rejected.text();
    assert.ok(!rejectedHtml.includes("</script><script>"));
    assert.ok(rejectedHtml.includes("\\u003c/script>"));
  } finally {
    globalThis.fetch = originalFetch;
    console.error = originalConsoleError;
  }
});
