/*
 * Status Portal front-end configuration (placeholders only).
 *
 * MVP: this file holds ONLY placeholder constants. No real Cognito ids, no real
 * API domain, and no token value is embedded. Deployment fills these in (e.g.
 * via a generated config.js during `deploy-frontend.sh`), or a Viewer completes
 * the Cognito Hosted UI flow which populates the token at runtime.
 *
 * See README.md for how these placeholders are replaced at deploy time.
 */
window.PORTAL_CONFIG = {
  // Cognito User Pool id (Requirement 9). Placeholder — replaced at deploy time.
  USER_POOL_ID: "REPLACE_WITH_USER_POOL_ID",
  // Cognito App Client id. Placeholder — replaced at deploy time.
  APP_CLIENT_ID: "REPLACE_WITH_APP_CLIENT_ID",
  // AWS region for the Cognito pool. Placeholder — replaced at deploy time.
  REGION: "REPLACE_WITH_REGION",
  // Cognito Hosted UI domain (without scheme). Placeholder.
  COGNITO_DOMAIN: "REPLACE_WITH_COGNITO_DOMAIN",
  // Base path for the Portal_API behind CloudFront. Same-origin /api by default,
  // so no real API domain is hard-coded here.
  API_BASE: "/api",
  // Redirect URI registered with the Cognito App Client. Placeholder.
  REDIRECT_URI: "REPLACE_WITH_REDIRECT_URI",
};
