// Document detail page + drill-through (addendum sections 3, 5, 6).
// Reads window.RECON = { gl:[rows], ar:[rows], ei:[rows], meta:{...}, drill:{...} }.
// One delegated listener resolves data-drill ids against RECON.drill. No filter
// logic is re-derived in the browser: the key lists come from the payload.
(function () {
  var R = window.RECON;
  if (!R) return;
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

  function meta(tab) { return R.meta[tab]; }
  function allRows(tab) { return R[tab]; }

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
    var rows = allRows(tab), f = window.__FILTER__;
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
  // distinct-key count = documents/vouchers at grain (addendum 3.2, 6.2)
  function distinctKeys(tab) {
    var f = window.__FILTER__;
    var rows = allRows(tab);
    if (f) {
      var keyset = { gl: f.glKeys, ar: f.arKeys, ei: f.eiKeys }[tab] || [];
      var set = {}; keyset.forEach(function (k) { set[String(k)] = 1; });
      rows = rows.filter(function (r) { return set[r._key]; });
    }
    var seen = {}; rows.forEach(function (r) { seen[r._key] = 1; });
    return Object.keys(seen).length;
  }
  function searchRows(tab) {
    var rows = baseRows(tab), q = state.search[tab].toLowerCase();
    if (!q) return rows;
    var cols = meta(tab)[state.mode[tab] === "all" ? "all" : "essential"];
    return rows.filter(function (r) {
      return cols.some(function (c) {
        var v = r[c]; if (Array.isArray(v)) v = v.join(" ");
        return String(v == null ? "" : v).toLowerCase().indexOf(q) >= 0;
      });
    });
  }
  function sortRows(tab, rows) {
    var s = state.sort[tab]; if (!s) return rows;
    var numeric = meta(tab).numeric.indexOf(s.col) >= 0;
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
    var m = meta(tab);
    if (tab === "ei" && col === "Status") return statusBadge(r[col]);
    if (col === "Status" || col === "Recon status") return reconBadge(r[col]);
    if (tab === "ei" && col === "Validation errors") return errlist(r._errors);
    var v = r[col];
    if (Array.isArray(v)) v = v.join(", ");
    v = esc(v);
    if (tab === "ei" && col === "Buyer name" && r._errors && r._errors.length &&
        (r._invoice_status === "FAILED" || r._invoice_status === "NOT_SUBMITTED")) {
      v += errlist(r._errors);
    }
    if (tab === "ar" && state.grain === "line" && !groupFirst &&
        m.doclevel_labels && m.doclevel_labels.indexOf(col) >= 0) {
      return '<span class="muted">' + v + "</span>";
    }
    return v;
  }

  function render() {
    var tab = state.tab, m = meta(tab);
    var fb = document.getElementById("dd-filterbar");
    var f = window.__FILTER__;
    if (f) {
      var grainWord = f.grain || "documents";
      fb.querySelector(".dd-fb-text").innerHTML =
        "Showing <strong>" + f.count + "</strong> " + esc(grainWord) +
        " &middot; " + esc(f.origin) + " &rsaquo; " + esc(f.label);
      fb.querySelector(".dd-clear").style.display = "";
      fb.querySelector(".dd-back").style.display = f.traced ? "" : "none";
    } else {
      fb.querySelector(".dd-fb-text").innerHTML = "Showing <strong>all</strong> documents";
      fb.querySelector(".dd-clear").style.display = "none";
      fb.querySelector(".dd-back").style.display = "none";
    }
    TABS.forEach(function (t) {
      var key = t[0];
      var el = document.getElementById("dd-subtab-" + key);
      el.querySelector(".dd-count").textContent = "(" + distinctKeys(key) + ")";
      el.classList.toggle("on", key === tab);
    });

    var rows = sortRows(tab, searchRows(tab));
    var cols = m[state.mode[tab] === "all" ? "all" : "essential"];
    var body = document.getElementById("dd-body");

    if (baseRows(tab).length === 0) {
      body.innerHTML =
        '<div class="dd-empty">No ' + esc(TABS.filter(function (t) { return t[0] === tab; })[0][1]) +
        " documents are associated with this selection.</div>";
      document.getElementById("dd-rowcount").textContent = "Showing 0 of " + m.total + " rows";
      renderControls();
      return;
    }

    var thead = "<tr>" + cols.map(function (c) {
      var arrow = state.sort[tab] && state.sort[tab].col === c ? (state.sort[tab].dir > 0 ? " ↑" : " ↓") : "";
      var num = m.numeric.indexOf(c) >= 0 ? " num" : "";
      return '<th class="' + num.trim() + '" data-col="' + esc(c) + '" title="' + esc(m.tooltips[c] || c) + '">' + esc(c) + arrow + "</th>";
    }).join("") + "</tr>";

    var seen = {};
    var trs = rows.map(function (r) {
      var groupFirst = true;
      if (tab === "ar" && state.grain === "line") { groupFirst = !seen[r._key]; seen[r._key] = 1; }
      var tds = cols.map(function (c) {
        var cls = m.numeric.indexOf(c) >= 0 ? ' class="num"'
          : (c === "Buyer name" || c === "Customer name" || c === "GL description" || c === "Validation errors" ? ' class="wrapcell"' : "");
        return "<td" + cls + ">" + cell(tab, r, c, groupFirst) + "</td>";
      }).join("");
      return '<tr data-key="' + esc(r._key) + '">' + tds + "</tr>";
    }).join("");

    var note = (tab === "ar" && state.grain === "line")
      ? '<p class="dd-note">Taxable value and VAT are document-level figures repeated on each line. They are counted once per voucher.</p>' : "";

    body.innerHTML = note +
      '<div class="tablewrap"><table class="dt"><thead>' + thead + "</thead><tbody>" + trs + "</tbody></table></div>";
    document.getElementById("dd-rowcount").textContent = "Showing " + rows.length + " of " + m.total + " rows";

    body.querySelectorAll("thead th").forEach(function (th) {
      th.addEventListener("click", function () {
        var c = th.getAttribute("data-col");
        var cur = state.sort[tab];
        state.sort[tab] = (cur && cur.col === c) ? { col: c, dir: -cur.dir } : { col: c, dir: 1 };
        render();
      });
    });
    body.querySelectorAll("tbody tr").forEach(function (tr) {
      tr.addEventListener("click", function () { traceDocument(tab, tr.getAttribute("data-key")); });
      tr.style.cursor = "pointer";
    });
    renderControls();
  }

  function renderControls() {
    var tab = state.tab;
    document.getElementById("dd-search").value = state.search[tab];
    document.getElementById("dd-colmode").textContent = state.mode[tab] === "all" ? "Essential columns" : "All columns";
    var grainBtn = document.getElementById("dd-grain");
    grainBtn.style.display = tab === "ar" ? "" : "none";
    grainBtn.textContent = state.grain === "voucher" ? "Line level" : "Voucher level";
  }

  function traceDocument(tab, key) {
    var doc = { gl: [], ar: [], ei: [] };
    doc[tab] = [key];
    var row = allRows(tab).filter(function (r) { return r._key === key; })[0];
    var voucher = row ? (row["Voucher number"] || row["E-invoice number"]) : null;
    if (voucher) {
      ["gl", "ar", "ei"].forEach(function (t) {
        if (t === tab) return;
        var field = t === "ei" ? "E-invoice number" : "Voucher number";
        allRows(t).forEach(function (r) {
          var rv = r[field]; if (rv == null) return;
          if (String(rv).replace(/^(CM|DM)-/i, "") === String(voucher).replace(/^(CM|DM)-/i, "")) doc[t].push(r._key);
        });
      });
    }
    var label = (tab === "ei" ? "e-invoice " : "voucher ") + (voucher || key);
    var originName = { gl: "GL register", ar: "Sales register", ei: "E-invoice" }[tab];
    window.__FILTER__ = {
      label: label, origin: "Traced from " + originName, traced: true,
      glKeys: doc.gl, arKeys: doc.ar, eiKeys: doc.ei,
      count: doc.gl.length + doc.ar.length + doc.ei.length, grain: "document"
    };
    render();
  }

  function toCSV() {
    var tab = state.tab, m = meta(tab);
    var cols = m[state.mode[tab] === "all" ? "all" : "essential"];
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
  function csvCell(v) { v = String(v == null ? "" : v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
  function slug(s) { return String(s || "all").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""); }
  function download() {
    var f = window.__FILTER__;
    var name = "document_detail_" + state.tab + "_" + slug(f ? f.label : "all") + ".csv";
    var blob = new Blob([toCSV()], { type: "text/csv" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name; a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  }

  function openDrill(id) {
    var d = R.drill && R.drill[id];
    if (!d) return;
    window.__FILTER__ = {
      label: d.label, origin: d.origin, grain: d.grain, count: d.count,
      glKeys: d.glKeys, arKeys: d.arKeys, eiKeys: d.eiKeys, traced: false
    };
    state.tab = "gl";
    if (typeof showDetailPage === "function") showDetailPage();
    render();
  }

  function wire() {
    TABS.forEach(function (t) {
      document.getElementById("dd-subtab-" + t[0]).addEventListener("click", function () { state.tab = t[0]; render(); });
    });
    document.getElementById("dd-search").addEventListener("input", function () { state.search[state.tab] = this.value; render(); });
    document.getElementById("dd-colmode").addEventListener("click", function () {
      state.mode[state.tab] = state.mode[state.tab] === "all" ? "essential" : "all"; render();
    });
    document.getElementById("dd-grain").addEventListener("click", function () {
      state.grain = state.grain === "voucher" ? "line" : "voucher"; render();
    });
    document.getElementById("dd-export").addEventListener("click", download);
    document.getElementById("dd-clear").addEventListener("click", function () { window.__FILTER__ = null; render(); });
    document.getElementById("dd-back").addEventListener("click", function () { if (window.__ddBack) window.__ddBack(); });

    // single delegated drill-through listener (addendum step 2)
    document.addEventListener("click", function (e) {
      var el = e.target.closest ? e.target.closest("[data-drill]") : null;
      if (!el) return;
      e.preventDefault();
      openDrill(el.getAttribute("data-drill"));
    });
    render();
  }

  window.openDocumentDetail = function (id) { openDrill(id); };
  window.__ddRender = render;

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wire);
  else wire();
})();
