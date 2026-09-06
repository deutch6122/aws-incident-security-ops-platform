/* Cognito authorization-code + PKCE client. Tokens live only in this module's
 * memory and expire according to expires_in. sessionStorage holds only the
 * short-lived state and PKCE verifier and is cleared after callback/logout. */
(function (global) {
  "use strict";

  var config = global.PORTAL_CONFIG || {};

  var FLOW_STATE_KEY = "portal_oauth_state";
  var PKCE_VERIFIER_KEY = "portal_pkce_verifier";
  var tokens = { accessToken: null, idToken: null, expiresAt: 0 };

  function base64Url(bytes) {
    var binary = "";
    bytes.forEach(function (value) { binary += String.fromCharCode(value); });
    return global.btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function randomValue(length) {
    var bytes = new Uint8Array(length);
    global.crypto.getRandomValues(bytes);
    return base64Url(bytes);
  }

  function statesMatch(sent, returned) {
    return typeof sent === "string" && sent.length > 0 && sent === returned;
  }

  async function challengeFor(verifier) {
    var digest = await global.crypto.subtle.digest(
      "SHA-256", new global.TextEncoder().encode(verifier)
    );
    return base64Url(new Uint8Array(digest));
  }

  function clearFlowData() {
    try {
      global.sessionStorage.removeItem(FLOW_STATE_KEY);
      global.sessionStorage.removeItem(PKCE_VERIFIER_KEY);
    } catch (e) { /* storage may be unavailable */ }
  }

  function clearTokens() {
    tokens = { accessToken: null, idToken: null, expiresAt: 0 };
  }

  function getAccessToken() {
    if (!tokens.accessToken || Date.now() >= tokens.expiresAt) {
      clearTokens();
      return null;
    }
    return tokens.accessToken;
  }

  function getIdToken() {
    if (!getAccessToken()) { return null; }
    return tokens.idToken;
  }

  function isSignedIn() { return !!getAccessToken(); }

  async function hostedUiLoginUrl() {
    var state = randomValue(24);
    var verifier = randomValue(48);
    var challenge = await challengeFor(verifier);
    global.sessionStorage.setItem(FLOW_STATE_KEY, state);
    global.sessionStorage.setItem(PKCE_VERIFIER_KEY, verifier);
    var params = new global.URLSearchParams({
      response_type: "code",
      client_id: config.APP_CLIENT_ID,
      redirect_uri: config.REDIRECT_URI,
      scope: config.OAUTH_SCOPES || "openid email profile",
      state: state,
      code_challenge: challenge,
      code_challenge_method: "S256",
    });
    return "https://" + config.COGNITO_DOMAIN + "/oauth2/authorize?" + params.toString();
  }

  async function beginLogin() {
    global.location.assign(await hostedUiLoginUrl());
  }

  async function handleCallback(search) {
    var params = new global.URLSearchParams(search || global.location.search);
    var returnedState = params.get("state");
    var sentState = global.sessionStorage.getItem(FLOW_STATE_KEY);
    var verifier = global.sessionStorage.getItem(PKCE_VERIFIER_KEY);
    if (params.get("error")) {
      clearFlowData();
      throw new Error("authentication was rejected");
    }
    if (!statesMatch(sentState, returnedState) || !verifier) {
      clearTokens();
      clearFlowData();
      throw new Error("OAuth state validation failed");
    }
    var code = params.get("code");
    if (!code) {
      clearFlowData();
      throw new Error("authorization code is missing");
    }
    var body = new global.URLSearchParams({
      grant_type: "authorization_code",
      client_id: config.APP_CLIENT_ID,
      code: code,
      redirect_uri: config.REDIRECT_URI,
      code_verifier: verifier,
    });
    var response = await global.fetch(
      "https://" + config.COGNITO_DOMAIN + "/oauth2/token",
      { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: body.toString() }
    );
    if (!response.ok) {
      clearTokens();
      clearFlowData();
      throw new Error("token exchange failed");
    }
    var payload = await response.json();
    var lifetime = Number(payload.expires_in);
    if (!payload.access_token || !Number.isFinite(lifetime) || lifetime <= 0) {
      clearTokens();
      clearFlowData();
      throw new Error("token response is invalid");
    }
    tokens = {
      accessToken: payload.access_token,
      idToken: payload.id_token || null,
      expiresAt: Date.now() + lifetime * 1000,
    };
    clearFlowData();
    return true;
  }

  function signOut() {
    clearTokens();
    clearFlowData();
    var params = new global.URLSearchParams({
      client_id: config.APP_CLIENT_ID,
      logout_uri: config.LOGOUT_URI,
    });
    global.location.assign("https://" + config.COGNITO_DOMAIN + "/logout?" + params.toString());
  }

  global.PortalAuth = {
    isSignedIn: isSignedIn,
    hostedUiLoginUrl: hostedUiLoginUrl,
    beginLogin: beginLogin,
    handleCallback: handleCallback,
    getAccessToken: getAccessToken,
    getIdToken: getIdToken,
    statesMatch: statesMatch,
    signOut: signOut,
  };
})(window);
