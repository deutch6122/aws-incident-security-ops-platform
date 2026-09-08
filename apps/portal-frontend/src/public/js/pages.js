/*
 * Page controllers for the Status Portal screens.
 *
 * Each page's inline script calls one of these init functions. They read data
 * via PortalApi and render into the page containers. Detail links are built with
 * PortalApi.buildStatusDetailPath / buildReportDetailPath so status_id / report_id
 * containing "/" are rejected (kept valid as `/api/.../{id}` path params).
 */
(function (global) {
  "use strict";

  var doc = global.document;

  function qs(id) {
    return doc.getElementById(id);
  }

  function text(value) {
    return value === undefined || value === null ? "" : String(value);
  }

  function getQueryParam(name) {
    var params = new global.URLSearchParams(global.location.search);
    return params.get(name);
  }

  function detailIdFor(item) {
    return item.status_id;
  }

  function statusTextFor(item) {
    return item.state || item.status || "";
  }

  function statusBodyFor(item) {
    return item.overview || item.message || statusTextFor(item);
  }

  function reportStorageKeyFor(report) {
    return report.s3_key || report.storage_key || "";
  }

  // --- login page ----------------------------------------------------------
  function initLoginPage() {
    var button = qs("login-button");
    if (!button) {
      return;
    }
    button.addEventListener("click", function () {
      global.PortalAuth.beginLogin().catch(function (err) {
        var message = qs("auth-message");
        if (message) { message.textContent = "エラー: " + err.message; }
      });
    });

    var logout = qs("logout-button");
    if (logout) {
      logout.addEventListener("click", function () { global.PortalAuth.signOut(); });
    }

    var params = new global.URLSearchParams(global.location.search);
    if (params.has("code") || params.has("error")) {
      global.PortalAuth.handleCallback(global.location.search)
        .then(function () {
          var message = qs("auth-message");
          if (message) { message.textContent = "ログインしました。"; }
          global.history.replaceState({}, doc.title, global.location.pathname);
        })
        .catch(function (err) {
          var message = qs("auth-message");
          if (message) { message.textContent = "エラー: " + err.message; }
        });
    }
  }

  // --- status list page ----------------------------------------------------
  function initStatusListPage() {
    var container = qs("status-list");
    if (!container) {
      return;
    }
    global.PortalApi.listStatus()
      .then(function (data) {
        var items = (data && data.items) || [];
        container.innerHTML = "";
        items.forEach(function (item) {
          var li = doc.createElement("li");
          var link = doc.createElement("a");
          link.textContent = text(item.title) + " (" + text(statusTextFor(item)) + ")";
          // Detail link uses a query param, and the API path is built safely.
          link.setAttribute(
            "href",
            "status-detail.html?id=" + encodeURIComponent(detailIdFor(item))
          );
          li.appendChild(link);
          container.appendChild(li);
        });
      })
      .catch(function (err) {
        container.textContent = "エラー: " + err.message;
      });
  }

  // --- status detail page --------------------------------------------------
  function initStatusDetailPage() {
    var container = qs("status-detail");
    if (!container) {
      return;
    }
    var id = getQueryParam("id");
    global.PortalApi.getStatus(id)
      .then(function (item) {
        container.innerHTML = "";
        var title = doc.createElement("h2");
        title.textContent = text(item.title);
        var body = doc.createElement("p");
        body.textContent = text(statusBodyFor(item));
        container.appendChild(title);
        if (item.kind === "security_finding") {
          var findingMeta = doc.createElement("dl");
          findingMeta.className = "finding-meta";
          var severityLabel = doc.createElement("dt");
          severityLabel.textContent = "重要度";
          var severityValue = doc.createElement("dd");
          severityValue.textContent = text(item.severity).toUpperCase();
          severityValue.className = "severity-critical";
          var resourceLabel = doc.createElement("dt");
          resourceLabel.textContent = "リソース種別";
          var resourceValue = doc.createElement("dd");
          resourceValue.textContent = text(item.resource_type);
          findingMeta.appendChild(severityLabel);
          findingMeta.appendChild(severityValue);
          findingMeta.appendChild(resourceLabel);
          findingMeta.appendChild(resourceValue);
          container.appendChild(findingMeta);
        }
        container.appendChild(body);
      })
      .catch(function (err) {
        container.textContent = "エラー: " + err.message;
      });
  }

  // --- report list page ----------------------------------------------------
  function initReportListPage() {
    var container = qs("report-list");
    if (!container) {
      return;
    }
    global.PortalApi.listReports()
      .then(function (data) {
        var reports = (data && data.reports) || [];
        container.innerHTML = "";
        reports.forEach(function (report) {
          var li = doc.createElement("li");
          var link = doc.createElement("a");
          link.textContent = text(report.title) + " [" + text(report.period) + "]";
          link.setAttribute(
            "href",
            "report-detail.html?id=" + encodeURIComponent(report.report_id)
          );
          li.appendChild(link);
          container.appendChild(li);
        });
      })
      .catch(function (err) {
        container.textContent = "エラー: " + err.message;
      });
  }

  // --- report detail page --------------------------------------------------
  function initReportDetailPage() {
    var container = qs("report-detail");
    if (!container) {
      return;
    }
    var id = getQueryParam("id");
    global.PortalApi.getReport(id)
      .then(function (report) {
        container.innerHTML = "";
        var title = doc.createElement("h2");
        title.textContent = text(report.title);
        var meta = doc.createElement("p");
        meta.textContent = "期間: " + text(report.period);
        var fileRef = doc.createElement("p");
        fileRef.textContent = "ファイル参照: " + text(reportStorageKeyFor(report));
        container.appendChild(title);
        container.appendChild(meta);
        container.appendChild(fileRef);
      })
      .catch(function (err) {
        container.textContent = "エラー: " + err.message;
      });
  }

  global.PortalPages = {
    initLoginPage: initLoginPage,
    initStatusListPage: initStatusListPage,
    initStatusDetailPage: initStatusDetailPage,
    initReportListPage: initReportListPage,
    initReportDetailPage: initReportDetailPage,
  };
})(window);
