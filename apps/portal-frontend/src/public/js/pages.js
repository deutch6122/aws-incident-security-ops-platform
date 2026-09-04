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

  // --- login page ----------------------------------------------------------
  function initLoginPage() {
    var button = qs("login-button");
    if (!button) {
      return;
    }
    button.addEventListener("click", function () {
      global.location.href = global.PortalAuth.hostedUiLoginUrl();
    });
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
          link.textContent = text(item.title) + " (" + text(item.state) + ")";
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
        body.textContent = text(item.overview || item.state);
        container.appendChild(title);
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
        fileRef.textContent = "ファイル参照: " + text(report.s3_key);
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
