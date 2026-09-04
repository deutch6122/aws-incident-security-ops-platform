/*
 * Shared Portal_API client.
 *
 * Calls the four Portal_API endpoints behind CloudFront:
 *   GET /api/status         — status list
 *   GET /api/status/{id}    — status detail
 *   GET /api/reports        — report list
 *   GET /api/reports/{id}   — report detail
 *
 * Authorization: each request carries the Cognito id/access token in the
 * Authorization header. Token acquisition is a placeholder here (Cognito Hosted
 * UI / SDK provides it at runtime); no real token value is embedded.
 *
 * status_id safety: the caller builds detail links from status_id via
 * buildStatusDetailPath(), which rejects ids containing "/" so they remain valid
 * `/api/status/{id}` path params (and URL-encodes other reserved characters).
 */
(function (global) {
  "use strict";

  var config = global.PORTAL_CONFIG || {};

  // --- token access (placeholder) -----------------------------------------
  // Reads the Cognito token from session storage where the Hosted UI / SDK
  // callback stores it. Returns null when not signed in. No token is hard-coded.
  function getIdToken() {
    try {
      return global.sessionStorage.getItem("portal_id_token");
    } catch (e) {
      return null;
    }
  }

  function getAccessToken() {
    try {
      return global.sessionStorage.getItem("portal_access_token");
    } catch (e) {
      return null;
    }
  }

  function authHeaders() {
    var headers = { Accept: "application/json" };
    var token = getIdToken() || getAccessToken();
    if (token) {
      // Bearer scheme; the token value comes from the Cognito flow at runtime.
      headers["Authorization"] = "Bearer " + token;
    }
    return headers;
  }

  function apiBase() {
    return config.API_BASE || "/api";
  }

  // status_id must not contain "/" so it fits `/api/status/{id}`. Reject such
  // ids and encode any other reserved characters.
  function buildStatusDetailPath(statusId) {
    var id = String(statusId);
    if (id.indexOf("/") !== -1) {
      throw new Error("invalid status_id: must not contain '/'");
    }
    return apiBase() + "/status/" + encodeURIComponent(id);
  }

  function buildReportDetailPath(reportId) {
    var id = String(reportId);
    if (id.indexOf("/") !== -1) {
      throw new Error("invalid report_id: must not contain '/'");
    }
    return apiBase() + "/reports/" + encodeURIComponent(id);
  }

  function request(path) {
    return global
      .fetch(path, { method: "GET", headers: authHeaders() })
      .then(function (resp) {
        if (resp.status === 401) {
          throw new Error("unauthorized");
        }
        if (!resp.ok) {
          throw new Error("request failed: " + resp.status);
        }
        return resp.json();
      });
  }

  var api = {
    getIdToken: getIdToken,
    authHeaders: authHeaders,
    buildStatusDetailPath: buildStatusDetailPath,
    buildReportDetailPath: buildReportDetailPath,
    listStatus: function () {
      return request(apiBase() + "/status");
    },
    getStatus: function (statusId) {
      return request(buildStatusDetailPath(statusId));
    },
    listReports: function () {
      return request(apiBase() + "/reports");
    },
    getReport: function (reportId) {
      return request(buildReportDetailPath(reportId));
    },
  };

  global.PortalApi = api;
})(window);
