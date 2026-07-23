// Document detail page (addendum sections 3, 4, 6). Renders three source tabs
// from window.__DETAIL__, all bound to window.__FILTER__ (null = show all).
(function () {
  var D = window.__DETAIL__;
  if (!D) return;
  var BADGE = {
    "Exact match": "ok", "Fully reconciled": "ok", "Amount mismatch": "warn",
    "Reconciled with differences": "warn", "Needs review": "warn",
    "Suggested combination": "info", "Missing in AR": "bad", "Missing in GL": "bad",
    "Missing in e-invoice": "bad", "Not e-invoiced": "bad", "Not booked": "bad",
    "Submitted but not accepted": "bad", "Billed but no revenue posted": "warn",
    "Revenue posted, not billed": "warn", "Out of scope by design": "neutral",
    "Out of period": "neutral", "Not a supply": "neutral"
  };
  var TABS = [["gl", "GL register"], ["ar", "Sales register"], ["ei", "E-invoice"]];
  var state = {
    tab: "gl",
    mode: { gl: "essential", ar: "essential", ei: "essential" },
    search: { gl: "", ar: "", ei: "" },
    sort: { gl: null, ar: null, ei: null },
    grain: "line"
  };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function reconBadge(s) { return '<span class="badge ' + (BADGE[s] || "neutral") + '">' + esc(s) + "</span>"; }
  function statusBadge(s) {
    var cls = (s === "CLEARED" || s === "REPORTED") ? "ok"
      : (s === "FAILED" || s === "NOT_SUBMITTED") ? "bad" : "neutral";
    return '<span class="badge ' + cls + '">' + esc(s) + "</span>";
  }
  function errlist(errs) {
    if (!errs || !errs.length) return "";
    return '<ul class="errlist">' + errs.map(function (e) { return "<li>" + esc(e) + "</li>"; }).join("") + "</ul>";
  }

  // rows for a tab: apply the active filter (null = all), then the search box
  function baseRows(tab) {
    var ds = D[tab], rows = ds.rows, f = window.__FILTER__;
    if (f) {
      var keyset = { gl: f.glKeys, ar: f.arKeys, ei: f.eiKeys }[tab] || [];
      var set = {}; keyset.forEach(function (k) { set[String(k)] = 1; });
      rows = rows.filter(function (r) { return set[r._key]; });
    }
    if (tab === "ar" && state.grain === "voucher") {
      var seen = {}; var out = [];
      rows.forEach(function (r) { if (!seen[r._key]) { seen[r._key] = 1; out.push(r); } });
      rows = out;
    }
    return rows;
  }
  function searchRows(tab) {
    var rows = baseRows(tab), q = state.search[tab].toLowerCase();
    if (!q) return rows;
    var cols = D[tab][state.mode[tab] === "all" ? "all" : "essential"];
    return rows.filter(function (r) {
      return cols.some(function (c) {
        var v = r[c]; if (Array.isArray(v)) v = v.join(" ");
        return String(v == null ? "" : v).toLowerCase().indexOf(q) >= 0;
      });
    });
  }
  function sortRows(tab, rows) {
    var s = state.sort[tab]; if (!s) return rows;
    var numeric = D[tab].numeric.indexOf(s.col) >= 0;
    var copy = rows.slice();
    copy.sort(function (a, b) {
      var x = a[s.col], y = b[s.col];
      if (Array.isArray(x)) x = x.join(" "); if (Array.isArray(y)) y = y.join(" ");
      if (numeric) {
        var nx = parseFloat(String(x).replace(/,/g, "")), ny = parseFloat(String(y).replace(/,/g, ""));
        nx = isNaN(nx) ? -Infinity : nx; ny = isNaN(ny) ? -Infinity : ny;
        return s.dir * (nx - ny);
      }
      return s.dir * String(x).localeCompare(String(y));
    });
    return copy;
  }

  function cell(tab, r, col, groupFirst) {
    var ds = D[tab];
    // status badges
    if (tab === "ei" && col === "Status") return statusBadge(r[col]);
    if (col === "Status" || col === "Recon status") return reconBadge(r[col]);
    if (tab === "ei" && col === "Validation errors") return errlist(r._errors);
    var v = r[col];
    if (Array.isArray(v)) v = v.join(", ");
    v = esc(v);
    // buyer name carries the ZATCA error text for failed/not-submitted rows
    if (tab === "ei" && col === "Buyer name" && r._errors && r._errors.length &&
        (r._invoice_status === "FAILED" || r._invoice_status === "NOT_SUBMITTED")) {
      v += errlist(r._errors);
    }
    // repeated document-level figures muted after the first line of a voucher
    if (tab === "ar" && state.grain === "line" && !groupFirst &&
        ds.doclevel_labels && ds.doclevel_labels.indexOf(col) >= 0) {
      return '<span class="muted">' + v + "</span>";
    }
    return v;
  }

  function render() {
    var tab = state.tab, ds = D[tab];
    // filter bar
    var fb = document.getElementById("dd-filterbar");
    var f = window.__FILTER__;
    if (f) {
      var grainWord = f.grain || "documents";
      fb.querySelector(".dd-fb-text").innerHTML =
        "Showing <strong>" + f.count + "</strong> " + esc(grainWord) +
        ' &middot; ' + esc(f.origin) + " &rsaquo; " + esc(f.label);
      fb.querySelector(".dd-clear").style.display = "";
      fb.querySelector(".dd-back").style.display = f.origin ? "" : "none";
    } else {
      fb.querySelector(".dd-fb-text").innerHTML = "Showing <strong>all</strong> documents";
      fb.querySelector(".dd-clear").style.display = "none";
      fb.querySelector(".dd-back").style.display = "none";
    }
    // sub-tab counts
    TABS.forEach(function (t) {
      var key = t[0];
      var prevTab = state.tab, prevSearch = state.search[key];
      // count = filtered rows for that tab, ignoring the search box
      var saved = state.tab; state.tab = key;
      var n = baseRows(key).length; state.tab = saved;
      var el = document.getElementById("dd-subtab-" + key);
      el.querySelector(".dd-count").textContent = "(" + n + ")";
      el.classList.toggle("on", key === tab);
    });

    var rows = sortRows(tab, searchRows(tab));
    var cols = ds[state.mode[tab] === "all" ? "all" : "essential"];
    var body = document.getElementById("dd-body");

    if (baseRows(tab).length === 0) {
      body.innerHTML =
        '<div class="dd-empty">No ' + esc(TABS.filter(function (t) { return t[0] === tab; })[0][1]) +
        " documents are associated with this selection.</div>";
      document.getElementById("dd-rowcount").textContent = "Showing 0 of " + ds.total + " rows";
      renderControls();
      return;
    }

    var thead = "<tr>" + cols.map(function (c) {
      var arrow = state.sort[tab] && state.sort[tab].col === c ? (state.sort[tab].dir > 0 ? " ↑" : " ↓") : "";
      var num = ds.numeric.indexOf(c) >= 0 ? " num" : "";
      return '<th class="' + num.trim() + '" data-col="' + esc(c) + '" title="' + esc(ds.tooltips[c] || c) + '">' + esc(c) + arrow + "</th>";
    }).join("") + "</tr>";

    var seen = {};
    var trs = rows.map(function (r) {
      var groupFirst = true;
      if (tab === "ar" && state.grain === "line") { groupFirst = !seen[r._key]; seen[r._key] = 1; }
      var tds = cols.map(function (c) {
        var num = ds.numeric.indexOf(c) >= 0 ? ' class="num"' : (c === "Buyer name" || c === "Customer name" || c === "GL description" || c === "Validation errors" ? ' class="wrapcell"' : "");
        return "<td" + num + ">" + cell(tab, r, c, groupFirst) + "</td>";
      }).join("");
      return '<tr data-key="' + esc(r._key) + '">' + tds + "</tr>";
    }).join("");

    var note = (tab === "ar" && state.grain === "line")
      ? '<p class="dd-note">Taxable value and VAT are document-level figures repeated on each line. They are counted once per voucher.</p>' : "";

    body.innerHTML = note +
      '<div class="tablewrap"><table class="dt"><thead>' + thead + "</thead><tbody>" + trs + "</tbody></table></div>";
    document.getElementById("dd-rowcount").textContent = "Showing " + rows.length + " of " + ds.total + " rows";

    // header sort handlers
    body.querySelectorAll("thead th").forEach(function (th) {
      th.addEventListener("click", function () {
        var c = th.getAttribute("data-col");
        var cur = state.sort[tab];
        state.sort[tab] = (cur && cur.col === c) ? { col: c, dir: -cur.dir } : { col: c, dir: 1 };
        render();
      });
    });
    // row click = trace this one document across all three tabs
    body.querySelectorAll("tbody tr").forEach(function (tr) {
      tr.addEventListener("click", function () { traceDocument(tab, tr.getAttribute("data-key")); });
      tr.style.cursor = "pointer";
    });
    renderControls();
  }

  function renderControls() {
    var tab = state.tab, ds = D[tab];
    document.getElementById("dd-search").value = state.search[tab];
    var modeBtn = document.getElementById("dd-colmode");
    modeBtn.textContent = state.mode[tab] === "all" ? "Essential columns" : "All columns";
    var grainBtn = document.getElementById("dd-grain");
    grainBtn.style.display = tab === "ar" ? "" : "none";
    grainBtn.textContent = state.grain === "voucher" ? "Line level" : "Voucher level";
  }

  function traceDocument(tab, key) {
    var ds = D[tab];
    var doc = { gl: [], ar: [], ei: [] };
    doc[tab] = [key];
    // find the same document in the other datasets by shared voucher identity
    var row = ds.rows.filter(function (r) { return r._key === key; })[0];
    var voucher = row ? (row["Voucher number"] || row["E-invoice number"]) : null;
    if (voucher) {
      ["gl", "ar", "ei"].forEach(function (t) {
        if (t === tab) return;
        var field = t === "ei" ? "E-invoice number" : "Voucher number";
        D[t].rows.forEach(function (r) {
          var rv = r[field]; if (rv == null) return;
          if (String(rv).replace(/^(CM|DM)-/i, "") === String(voucher).replace(/^(CM|DM)-/i, "")) doc[t].push(r._key);
        });
      });
    }
    var label = (tab === "ei" ? "e-invoice " : "voucher ") + esc(voucher || key);
    var originName = { gl: "GL register", ar: "Sales register", ei: "E-invoice" }[tab];
    window.__FILTER__ = {
      label: label, origin: "Traced from " + originName, traced: true,
      glKeys: doc.gl, arKeys: doc.ar, eiKeys: doc.ei,
      count: doc.gl.length + doc.ar.length + doc.ei.length, grain: "document"
    };
    render();
  }

  function toCSV() {
    var tab = state.tab, ds = D[tab];
    var cols = ds[state.mode[tab] === "all" ? "all" : "essential"];
    var rows = sortRows(tab, searchRows(tab));
    var lines = [cols.map(csvCell).join(",")];
    rows.forEach(function (r) {
      lines.push(cols.map(function (c) {
        var v = r[c]; if (Array.isArray(v)) v = v.join("; ");
        return csvCell(v);
      }).join(","));
    });
    return lines.join("\n");
  }
  function csvCell(v) {
    v = String(v == null ? "" : v);
    return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
  }
  function slug(s) { return String(s || "all").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""); }
  function download() {
    var f = window.__FILTER__;
    var name = "document_detail_" + state.tab + "_" + slug(f ? f.label : "all") + ".csv";
    var blob = new Blob([toCSV()], { type: "text/csv" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name; a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  }

  function wire() {
    TABS.forEach(function (t) {
      document.getElementById("dd-subtab-" + t[0]).addEventListener("click", function () {
        state.tab = t[0]; render();
      });
    });
    document.getElementById("dd-search").addEventListener("input", function () {
      state.search[state.tab] = this.value; render();
    });
    document.getElementById("dd-colmode").addEventListener("click", function () {
      state.mode[state.tab] = state.mode[state.tab] === "all" ? "essential" : "all"; render();
    });
    document.getElementById("dd-grain").addEventListener("click", function () {
      state.grain = state.grain === "voucher" ? "line" : "voucher"; render();
    });
    document.getElementById("dd-export").addEventListener("click", download);
    document.getElementById("dd-clear").addEventListener("click", function () {
      window.__FILTER__ = null; render();
    });
    document.getElementById("dd-back").addEventListener("click", function () {
      if (window.__ddBack) window.__ddBack();
    });
    render();
  }

  // expose so origin pages can open this page pre-filtered (checkpoint 4)
  window.openDocumentDetail = function (filter) { window.__FILTER__ = filter; showDetailPage(); render(); };
  window.__ddRender = render;

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wire);
  else wire();
})();
