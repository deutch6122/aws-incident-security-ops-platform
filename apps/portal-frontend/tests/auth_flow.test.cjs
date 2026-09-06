const assert = require("node:assert/strict");
const crypto = require("node:crypto").webcrypto;
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const { TextEncoder } = require("node:util");

const source = fs.readFileSync(
  path.join(__dirname, "../src/public/js/auth.js"),
  "utf8"
);

function loadAuth(fetchImpl) {
  const values = new Map();
  const redirects = [];
  let now = 1_700_000_000_000;
  const sessionStorage = {
    getItem: (key) => values.has(key) ? values.get(key) : null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  };
  const window = {
    PORTAL_CONFIG: {
      APP_CLIENT_ID: "client-id",
      COGNITO_DOMAIN: "example.auth.ap-northeast-1.amazoncognito.com",
      REDIRECT_URI: "https://portal.example/callback",
      LOGOUT_URI: "https://portal.example/",
      OAUTH_SCOPES: "openid email profile",
    },
    URLSearchParams,
    TextEncoder,
    Uint8Array,
    crypto,
    btoa: (value) => Buffer.from(value, "binary").toString("base64"),
    sessionStorage,
    fetch: fetchImpl,
    location: {
      search: "",
      assign: (url) => redirects.push(url),
    },
    Date: class extends Date { static now() { return now; } },
  };
  vm.runInNewContext(source, { window, Uint8Array, Date: window.Date });
  return {
    auth: window.PortalAuth,
    values,
    redirects,
    advance: (milliseconds) => { now += milliseconds; },
  };
}

test("authorization request uses code flow, PKCE S256, and state", async () => {
  const fixture = loadAuth(async () => { throw new Error("fetch must not run"); });
  const url = new URL(await fixture.auth.hostedUiLoginUrl());
  assert.equal(url.pathname, "/oauth2/authorize");
  assert.equal(url.searchParams.get("response_type"), "code");
  assert.equal(url.searchParams.get("code_challenge_method"), "S256");
  assert.ok(url.searchParams.get("code_challenge"));
  assert.equal(url.searchParams.get("state"), fixture.values.get("portal_oauth_state"));
  assert.ok(fixture.values.get("portal_pkce_verifier"));
});

test("state mismatch rejects before token exchange and stores no token", async () => {
  let fetchCalls = 0;
  const fixture = loadAuth(async () => { fetchCalls += 1; });
  await fixture.auth.hostedUiLoginUrl();
  await assert.rejects(
    fixture.auth.handleCallback("?code=abc&state=wrong"),
    /state validation failed/
  );
  assert.equal(fetchCalls, 0);
  assert.equal(fixture.auth.getAccessToken(), null);
  assert.equal(fixture.values.has("portal_oauth_state"), false);
  assert.equal(fixture.values.has("portal_pkce_verifier"), false);
});

test("valid callback exchanges code, keeps token in memory, and enforces expiry", async () => {
  let request;
  const fixture = loadAuth(async (url, options) => {
    request = { url, options };
    return {
      ok: true,
      json: async () => ({ access_token: "access-value", id_token: "id-value", expires_in: 60 }),
    };
  });
  const login = new URL(await fixture.auth.hostedUiLoginUrl());
  const state = login.searchParams.get("state");
  await fixture.auth.handleCallback("?code=auth-code&state=" + encodeURIComponent(state));
  assert.equal(request.url.includes("/oauth2/token"), true);
  assert.equal(request.options.body.includes("grant_type=authorization_code"), true);
  assert.equal(request.options.body.includes("code_verifier="), true);
  assert.equal(fixture.auth.getAccessToken(), "access-value");
  assert.equal([...fixture.values.keys()].some((key) => key.includes("token")), false);
  fixture.advance(60_001);
  assert.equal(fixture.auth.getAccessToken(), null);
});

test("logout clears memory and flow data then redirects to Cognito logout", async () => {
  const fixture = loadAuth(async () => ({
    ok: true,
    json: async () => ({ access_token: "access-value", expires_in: 60 }),
  }));
  const login = new URL(await fixture.auth.hostedUiLoginUrl());
  await fixture.auth.handleCallback("?code=ok&state=" + login.searchParams.get("state"));
  fixture.auth.signOut();
  assert.equal(fixture.auth.getAccessToken(), null);
  assert.equal(fixture.values.size, 0);
  const logout = new URL(fixture.redirects.at(-1));
  assert.equal(logout.pathname, "/logout");
  assert.equal(logout.searchParams.get("logout_uri"), "https://portal.example/");
});
