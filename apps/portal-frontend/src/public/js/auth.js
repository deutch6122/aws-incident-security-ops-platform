/*
 * Cognito auth helpers (MVP placeholders).
 *
 * The real login uses the Cognito Hosted UI: the login button redirects the
 * Viewer to the Hosted UI, and the callback stores the id/access token in
 * session storage where api.js reads it. This file only builds the redirect URL
 * from PORTAL_CONFIG placeholders and reads/clears the stored token. No token
 * value and no real Cognito domain are embedded here.
 */
(function (global) {
  "use strict";

  var config = global.PORTAL_CONFIG || {};

  function isSignedIn() {
    try {
      return !!global.sessionStorage.getItem("portal_id_token");
    } catch (e) {
      return false;
    }
  }

  // Build the Cognito Hosted UI login URL from placeholders. At deploy time the
  // placeholders are replaced with the real pool/client/domain values.
  function hostedUiLoginUrl() {
    var domain = config.COGNITO_DOMAIN || "REPLACE_WITH_COGNITO_DOMAIN";
    var clientId = config.APP_CLIENT_ID || "REPLACE_WITH_APP_CLIENT_ID";
    var redirect = config.REDIRECT_URI || "REPLACE_WITH_REDIRECT_URI";
    return (
      "https://" +
      domain +
      "/login?response_type=token&client_id=" +
      encodeURIComponent(clientId) +
      "&redirect_uri=" +
      encodeURIComponent(redirect)
    );
  }

  function signOut() {
    try {
      global.sessionStorage.removeItem("portal_id_token");
      global.sessionStorage.removeItem("portal_access_token");
    } catch (e) {
      /* ignore */
    }
  }

  global.PortalAuth = {
    isSignedIn: isSignedIn,
    hostedUiLoginUrl: hostedUiLoginUrl,
    signOut: signOut,
  };
})(window);
