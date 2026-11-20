"use strict";
(function () {
  var $ = function (id) { return document.getElementById(id); };

  var state = {
    capabilities: null,
    activeTab: "standardize",
    std: { source: null, mapping: { mappings: [], group_cross_healing: {} }, suggested: null },
    matchLeft: { source: null, mapping: { mappings: [], group_cross_healing: {} }, suggested: null },
    matchRight: { source: null, mapping: { mappings: [], group_cross_healing: {} }, suggested: null },
    leftRoster: { source: null },
    rightRoster: { source: null },
    dedup: { source: null, mapping: { mappings: [], group_cross_healing: {} }, suggested: null, jobId: null, offset: 0, selectedRowIndex: null },
    matchJobId: null,
    matchOffset: 0,
    selectedPair: null
  };

  var STD_SELECT_IDS = [
    "column_mode", "invalid_policy", "couple_split_mode", "phone_format",
    "extension_mode", "address_case", "country_format", "company_case",
    "company_style", "person_case", "person_format"
  ];
  var STD_CHECK_IDS = [
    "include_audit_cols", "include_matching_keys", "enable_cross_healing",
    "rescue_misplaced_fields", "infer_blank_fields", "split_secondary_unit",
    "enable_geocoding", "use_nickname_root", "email_strip_subaddress",
    "email_canonicalize_gmail_dots", "email_heal_typos", "csv_formula_guard"
  ];
  var PROFILE_DEFAULTS = {
    FIRM: [0.72, 0.50], OFFICE: [0.70, 0.50], CONTACT: [0.70, 0.50],
    PARTNERSHIP: [0.70, 0.50], TEAM: [0.70, 0.50], CUSTOM: [0.70, 0.50]
  };
  var LIVE_FIELDS = [
    ["organization", "Company / Organization"], ["person_name", "Person Full Name"],
    ["job_title", "Job Title"], ["street1", "Street Line 1"], ["street2", "Street Line 2"],
    ["city", "City"], ["state", "State / Province"], ["postal_code", "Postal / ZIP"],
    ["country", "Country"], ["phone", "Phone"], ["fax", "Fax"], ["email", "Email"],
    ["website", "Website URL"], ["social", "Social URL / Handle"], ["crd", "FINRA CRD"],
    ["external_id", "External ID"]
  ];

  function el(tag, text, cls) {
    var node = document.createElement(tag);
    if (text !== undefined && text !== null) { node.textContent = String(text); }
    if (cls) { node.className = cls; }
    return node;
  }
  function clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }

  function setStatus(text, kind) {
    var s = $("global-status");
    s.textContent = text;
    s.className = "status-msg " + (kind || "");
  }

  function apiHeaders(extra) {
    var headers = extra ? Object.assign({}, extra) : {};
    var key = $("api-key-input").value.trim();
    if (key) { headers["X-API-Key"] = key; }
    return headers;
  }

  function formatApiError(data, status) {
    if (data && typeof data.detail === "string") { return data.detail; }
    if (data && Array.isArray(data.detail) && data.detail.length && data.detail[0].msg) {
      return String(data.detail[0].msg);
    }
    return "HTTP " + status;
  }

  function apiFetch(url, options) {
    var opts = Object.assign({}, options || {});
    opts.headers = apiHeaders(opts.headers);
    return fetch(url, opts).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) {
          throw new Error(formatApiError(data, res.status));
        }
        return data;
      });
    });
  }

  function downloadFile(url, fallbackName) {
    setStatus("Preparing download...");
    return fetch(url, { headers: apiHeaders() }).then(function (res) {
      if (!res.ok) {
        return res.json().catch(function () { return {}; }).then(function (d) {
          throw new Error(formatApiError(d, res.status));
        });
      }
      var disp = res.headers.get("Content-Disposition") || "";
      var m = disp.match(/filename="?([^"]+)"?/i);
      var fname = (m && m[1]) || fallbackName;
      return res.blob().then(function (blob) {
        var href = URL.createObjectURL(blob);
        var a = document.createElement("a");
        a.href = href;
        a.download = fname;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(function () { URL.revokeObjectURL(href); }, 1000);
        setStatus("Downloaded " + fname, "ok");
      });
    }).catch(function (err) { setStatus(err.message, "err"); });
  }

  function renderKpis(container, pairs) {
    clear(container);
    pairs.forEach(function (kv) {
      var box = el("div", null, "kpi");
      box.appendChild(el("div", kv[1], "val"));
      box.appendChild(el("div", kv[0], "lbl"));
      container.appendChild(box);
    });
  }

  function buildSourceWidget(slotId, onLoaded, compact) {
    var host = $(slotId);
    clear(host);
    var drop = el("div", "Drop CSV, TSV, PSV, TXT, XLSX, JSON, JSONL, or Parquet here — or click to browse", "dropzone");
    var fileIn = document.createElement("input");
    fileIn.type = "file";
    fileIn.accept = ".csv,.tsv,.psv,.txt,.xlsx,.json,.jsonl,.ndjson,.parquet";
    fileIn.hidden = true;

    var delimSel = el("select");
    [["", "Auto Delimiter"], [",", "Comma (,)"], ["\\t", "Tab (\\t)"], ["|", "Pipe (|)"], [";", "Semicolon (;)"]].forEach(function (p) {
      var o = el("option", p[1]);
      o.value = p[0];
      delimSel.appendChild(o);
    });
    var sheetSel = el("select");
    sheetSel.hidden = true;
    var reinspectBtn = el("button", "Reload Dialect/Sheet", "btn-secondary");
    reinspectBtn.type = "button";
    reinspectBtn.hidden = true;
    var metaBadge = el("span", "No file loaded", "muted");

    var pathWrap = el("div", null, "inline-field");
    var pathIn = document.createElement("input");
    pathIn.type = "text";
    pathIn.placeholder = "Local file path (zero-copy streaming for large files)";
    var pathBtn = el("button", "Load Path", "btn-secondary");
    pathBtn.type = "button";
    pathWrap.appendChild(pathIn);
    pathWrap.appendChild(pathBtn);
    pathWrap.hidden = !(state.capabilities && state.capabilities.local_paths_enabled);

    var currentSourceId = null;

    function handlePayload(data) {
      currentSourceId = data.source_id;
      clear(sheetSel);
      if (data.sheet_names && data.sheet_names.length > 0) {
        data.sheet_names.forEach(function (sn) {
          var opt = el("option", sn);
          opt.value = sn;
          if (data.format_spec && data.format_spec.sheet_name === sn) { opt.selected = true; }
          sheetSel.appendChild(opt);
        });
        sheetSel.hidden = false;
      } else {
        sheetSel.hidden = true;
      }
      reinspectBtn.hidden = false;
      var fmt = data.format_spec ? data.format_spec.format.toUpperCase() : "";
      var rowTxt = data.total_rows !== null && data.total_rows !== undefined ? data.total_rows + " rows" : "streaming";
      metaBadge.textContent = data.file_name + " (" + fmt + ", " + data.columns.length + " cols, " + rowTxt + ")";
      metaBadge.className = "pill ok";
      onLoaded(data);
    }

    function uploadFile(file) {
      var fd = new FormData();
      fd.append("file", file);
      if (delimSel.value) { fd.append("delimiter", delimSel.value); }
      setStatus("Uploading and inspecting " + file.name + "...");
      fetch("/ui/api/upload", { method: "POST", headers: apiHeaders(), body: fd })
        .then(function (r) {
          return r.json().catch(function () { return {}; }).then(function (d) {
            if (!r.ok) { throw new Error(formatApiError(d, r.status)); }
            return d;
          });
        })
        .then(function (d) { handlePayload(d); setStatus("Loaded " + d.file_name, "ok"); })
        .catch(function (err) { setStatus(err.message, "err"); });
    }

    drop.addEventListener("click", function () { fileIn.click(); });
    drop.addEventListener("dragover", function (e) { e.preventDefault(); drop.classList.add("drag"); });
    drop.addEventListener("dragleave", function () { drop.classList.remove("drag"); });
    drop.addEventListener("drop", function (e) {
      e.preventDefault();
      drop.classList.remove("drag");
      if (e.dataTransfer && e.dataTransfer.files.length) { uploadFile(e.dataTransfer.files[0]); }
    });
    fileIn.addEventListener("change", function () {
      if (fileIn.files && fileIn.files.length) {
        var chosen = fileIn.files[0];
        fileIn.value = "";
        uploadFile(chosen);
      }
    });

    pathBtn.addEventListener("click", function () {
      var p = pathIn.value.trim();
      if (!p) { return; }
      setStatus("Inspecting local path...");
      apiFetch("/ui/api/inspect-path", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: p, delimiter: delimSel.value || null })
      }).then(function (d) { handlePayload(d); setStatus("Loaded " + d.file_name, "ok"); })
        .catch(function (err) { setStatus(err.message, "err"); });
    });

    reinspectBtn.addEventListener("click", function () {
      if (!currentSourceId) { return; }
      setStatus("Re-inspecting file dialect/sheet...");
      apiFetch("/ui/api/reinspect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_id: currentSourceId,
          delimiter: delimSel.value || null,
          sheet_name: sheetSel.hidden ? null : sheetSel.value
        })
      }).then(function (d) { handlePayload(d); setStatus("Reloaded " + d.file_name, "ok"); })
        .catch(function (err) { setStatus(err.message, "err"); });
    });

    host.appendChild(fileIn);
    if (!compact) { host.appendChild(drop); } else {
      var chooseBtn = el("button", "Upload Roster File", "btn-secondary");
      chooseBtn.type = "button";
      chooseBtn.addEventListener("click", function () { fileIn.click(); });
      host.appendChild(chooseBtn);
    }
    var ctrl = el("div", null, "source-controls");
    ctrl.appendChild(pathWrap);
    ctrl.appendChild(delimSel);
    ctrl.appendChild(sheetSel);
    ctrl.appendChild(reinspectBtn);
    ctrl.appendChild(metaBadge);
    host.appendChild(ctrl);
  }

  function renderMapper(slotId, targetState) {
    var host = $(slotId);
    clear(host);
    if (!targetState.source) { host.hidden = true; return; }
    host.hidden = false;

    var columns = targetState.source.columns || [];
    var samples = targetState.source.sample_rows || [];
    var roles = (state.capabilities && state.capabilities.roles) || [];

    var toolbar = el("div", null, "mapper-toolbar");
    var searchIn = document.createElement("input");
    searchIn.type = "search";
    searchIn.placeholder = "Search " + columns.length + " columns...";
    var mappedOnlyLbl = el("label", null, "check");
    var mappedOnlyCb = document.createElement("input");
    mappedOnlyCb.type = "checkbox";
    mappedOnlyLbl.appendChild(mappedOnlyCb);
    mappedOnlyLbl.appendChild(document.createTextNode("Mapped Only"));

    var autoBtn = el("button", "Auto-Detect", "btn-secondary");
    autoBtn.type = "button";
    var clearBtn = el("button", "Clear All", "btn-secondary");
    clearBtn.type = "button";
    var countBadge = el("span", "", "pill");

    toolbar.appendChild(searchIn);
    toolbar.appendChild(mappedOnlyLbl);
    toolbar.appendChild(autoBtn);
    toolbar.appendChild(clearBtn);
    toolbar.appendChild(countBadge);
    host.appendChild(toolbar);

    var groupHealBar = el("div", null, "signal-pills");
    host.appendChild(groupHealBar);

    var wrap = el("div", null, "table-wrap");
    var table = el("table");
    var thead = el("thead");
    var hr = el("tr");
    ["Column", "Target Role", "Healing Group", "Sample Values"].forEach(function (h) { hr.appendChild(el("th", h)); });
    thead.appendChild(hr);
    table.appendChild(thead);
    var tbody = el("tbody");
    table.appendChild(tbody);
    wrap.appendChild(table);
    host.appendChild(wrap);

    function mappingByCol() {
      var map = {};
      (targetState.mapping.mappings || []).forEach(function (m) { map[m.column] = m; });
      return map;
    }

    function renderGroupHealToggles() {
      clear(groupHealBar);
      var groups = [];
      (targetState.mapping.mappings || []).forEach(function (m) {
        if (groups.indexOf(m.group_id) === -1) { groups.push(m.group_id); }
      });
      if (!groups.length) { return; }
      groupHealBar.appendChild(el("span", "Group Cross-Healing:", "muted"));
      groups.forEach(function (gid) {
        var lbl = el("label");
        var cb = document.createElement("input");
        cb.type = "checkbox";
        var cur = targetState.mapping.group_cross_healing;
        cb.checked = cur && Object.prototype.hasOwnProperty.call(cur, gid) ? Boolean(cur[gid]) : true;
        cb.addEventListener("change", function () {
          targetState.mapping.group_cross_healing[gid] = cb.checked;
        });
        lbl.appendChild(cb);
        lbl.appendChild(document.createTextNode(gid));
        groupHealBar.appendChild(lbl);
      });
    }

    function updateMapping(col, role, groupId) {
      var list = (targetState.mapping.mappings || []).filter(function (m) { return m.column !== col; });
      if (role) {
        list.push({ column: col, role: role, group_id: (groupId || "primary").trim() || "primary" });
      }
      targetState.mapping.mappings = list;
      countBadge.textContent = list.length + " mapped";
      renderGroupHealToggles();
    }

    function drawRows() {
      clear(tbody);
      var q = searchIn.value.trim().toLowerCase();
      var onlyMapped = mappedOnlyCb.checked;
      var byCol = mappingByCol();
      countBadge.textContent = (targetState.mapping.mappings || []).length + " mapped";

      columns.forEach(function (col) {
        var existing = byCol[col];
        if (onlyMapped && !existing) { return; }
        if (q && col.toLowerCase().indexOf(q) === -1 && (!existing || existing.role.indexOf(q) === -1)) { return; }

        var tr = el("tr");
        tr.appendChild(el("td", col, "mono"));

        var roleTd = el("td");
        var roleSel = el("select");
        var noneOpt = el("option", "-- Ignore --");
        noneOpt.value = "";
        roleSel.appendChild(noneOpt);
        roles.forEach(function (r) {
          var o = el("option", r);
          o.value = r;
          if (existing && existing.role === r) { o.selected = true; }
          roleSel.appendChild(o);
        });
        roleTd.appendChild(roleSel);
        tr.appendChild(roleTd);

        var grpTd = el("td");
        var grpIn = document.createElement("input");
        grpIn.type = "text";
        grpIn.setAttribute("list", "group-suggestions");
        grpIn.value = existing ? existing.group_id : "primary";
        grpIn.disabled = !existing;
        grpTd.appendChild(grpIn);
        tr.appendChild(grpTd);

        var sampVals = [];
        samples.forEach(function (sr) {
          var v = sr[col];
          if (v !== undefined && v !== null && String(v).trim() && sampVals.length < 3) {
            sampVals.push(String(v).slice(0, 42));
          }
        });
        tr.appendChild(el("td", sampVals.join(" | "), "muted mono"));

        roleSel.addEventListener("change", function () {
          grpIn.disabled = !roleSel.value;
          updateMapping(col, roleSel.value, grpIn.value);
        });
        grpIn.addEventListener("change", function () {
          if (roleSel.value) { updateMapping(col, roleSel.value, grpIn.value); }
        });

        tbody.appendChild(tr);
      });
      renderGroupHealToggles();
    }

    searchIn.addEventListener("input", drawRows);
    mappedOnlyCb.addEventListener("change", drawRows);
    autoBtn.addEventListener("click", function () {
      targetState.mapping = JSON.parse(JSON.stringify(targetState.suggested || { mappings: [], group_cross_healing: {} }));
      drawRows();
    });
    clearBtn.addEventListener("click", function () {
      targetState.mapping = { mappings: [], group_cross_healing: {} };
      drawRows();
    });

    drawRows();
  }

  function gatherStdOptions() {
    var out = {};
    STD_SELECT_IDS.forEach(function (id) { out[id] = $("opt-" + id).value; });
    STD_CHECK_IDS.forEach(function (id) { out[id] = $("opt-" + id).checked; });
    out.default_country = $("opt-default_country").value.trim() || "US";
    var padRaw = $("opt-id_pad_width").value.trim();
    out.id_pad_width = padRaw ? parseInt(padRaw, 10) : null;
    return out;
  }

  function applyStdOptions(opts) {
    if (!opts) { return; }
    STD_SELECT_IDS.forEach(function (id) {
      if (opts[id] !== undefined && $("opt-" + id)) { $("opt-" + id).value = opts[id]; }
    });
    STD_CHECK_IDS.forEach(function (id) {
      if (opts[id] !== undefined && $("opt-" + id)) { $("opt-" + id).checked = Boolean(opts[id]); }
    });
    if (opts.default_country !== undefined) { $("opt-default_country").value = opts.default_country; }
    $("opt-id_pad_width").value = opts.id_pad_width !== null && opts.id_pad_width !== undefined ? String(opts.id_pad_width) : "";
  }

  function gatherMatchingOptions() {
    var sigs = [];
    document.querySelectorAll(".match-sig-cb:checked").forEach(function (cb) { sigs.push(cb.value); });
    if (state.activeTab === "dedup") {
      var dThr = parseFloat($("dedup-threshold").value);
      var dPot = (PROFILE_DEFAULTS[$("dedup-profile").value] || [0.70, 0.50])[1];
      return {
        profile: $("dedup-profile").value,
        auto_standardize: $("dedup-auto-std").checked,
        match_threshold: dThr,
        potential_threshold: isNaN(dThr) ? dPot : Math.min(dPot, dThr),
        enabled_signals: sigs,
        switchboard_min_shared: parseInt($("match-switchboard").value, 10) || 4,
        synthetic_policy: $("dedup-synthetic").value,
        default_country: $("dedup-country").value.trim() || "US"
      };
    }
    return {
      profile: $("match-profile").value,
      auto_standardize: $("match-auto-std").checked,
      match_threshold: parseFloat($("match-threshold").value),
      potential_threshold: parseFloat($("match-potential-threshold").value),
      enabled_signals: sigs,
      switchboard_min_shared: parseInt($("match-switchboard").value, 10) || 4,
      synthetic_policy: $("match-synthetic").value,
      default_country: $("match-country").value.trim() || "US"
    };
  }

  function applyMatchingOptions(opts) {
    if (!opts) { return; }
    if (opts.profile) { $("match-profile").value = opts.profile; $("dedup-profile").value = opts.profile; }
    if (opts.auto_standardize !== undefined) {
      $("match-auto-std").checked = Boolean(opts.auto_standardize);
      $("dedup-auto-std").checked = Boolean(opts.auto_standardize);
    }
    if (opts.match_threshold !== undefined) {
      $("match-threshold").value = opts.match_threshold;
      $("dedup-threshold").value = opts.match_threshold;
    }
    if (opts.potential_threshold !== undefined) { $("match-potential-threshold").value = opts.potential_threshold; }
    if (opts.switchboard_min_shared !== undefined) { $("match-switchboard").value = opts.switchboard_min_shared; }
    if (opts.synthetic_policy) {
      $("match-synthetic").value = opts.synthetic_policy;
      $("dedup-synthetic").value = opts.synthetic_policy;
    }
    if (opts.default_country) {
      $("match-country").value = opts.default_country;
      $("dedup-country").value = opts.default_country;
    }
    if (opts.enabled_signals) {
      document.querySelectorAll(".match-sig-cb").forEach(function (cb) {
        cb.checked = opts.enabled_signals.indexOf(cb.value) !== -1;
      });
    }
  }

  function renderPager(containerId, offset, pageCount, total, limit, onPage) {
    var box = $(containerId);
    clear(box);
    if (!total) { return; }
    var start = offset + 1;
    var end = offset + pageCount;
    var prevBtn = el("button", "Prev", "btn-secondary");
    prevBtn.type = "button";
    prevBtn.disabled = offset <= 0;
    prevBtn.addEventListener("click", function () { onPage(Math.max(0, offset - limit)); });
    var nextBtn = el("button", "Next", "btn-secondary");
    nextBtn.type = "button";
    nextBtn.disabled = end >= total;
    nextBtn.addEventListener("click", function () { onPage(offset + limit); });
    box.appendChild(prevBtn);
    box.appendChild(el("span", "Showing " + start + "-" + end + " of " + total, "muted"));
    box.appendChild(nextBtn);
  }

  function renderStdPreview(data) {
    $("std-results-card").hidden = false;
    renderKpis($("std-kpi-strip"), [
      ["Previewed Rows", data.preview_count],
      ["Cells Modified", data.cells_changed],
      ["Cells Cleared", data.cells_cleared],
      ["Invalid Kept", data.invalid_cells],
      ["Output Columns", data.output_columns.length]
    ]);
    var wrap = $("std-preview-wrap");
    clear(wrap);
    if (!data.rows || !data.rows.length) {
      wrap.appendChild(el("p", "No rows to preview.", "muted"));
      return;
    }
    var mappedCols = (state.std.mapping.mappings || []).map(function (m) { return m.column; });
    var inputCols = data.input_columns || [];
    var showCols = data.output_columns.filter(function (c) {
      return mappedCols.indexOf(c) !== -1 || inputCols.indexOf(c) === -1;
    });
    if (!showCols.length) { showCols = data.output_columns.slice(0, 10); }

    var table = el("table");
    var thead = el("thead");
    var hr = el("tr");
    hr.appendChild(el("th", "#"));
    showCols.forEach(function (c) { hr.appendChild(el("th", c)); });
    hr.appendChild(el("th", "Healing Actions"));
    thead.appendChild(hr);
    table.appendChild(thead);

    var tbody = el("tbody");
    data.rows.forEach(function (r) {
      var tr = el("tr");
      var idxTd = el("td", String(r.row_index + 1), "mono");
      if (r.split_count > 1) {
        idxTd.appendChild(document.createTextNode(" "));
        idxTd.appendChild(el("span", "SPLIT x" + r.split_count, "pill heal"));
      }
      tr.appendChild(idxTd);
      showCols.forEach(function (c) {
        var td = el("td", null, "mono");
        var isAppStd = c.endsWith("_std") && r.before[c] === undefined && r.cell_changes[c.slice(0, -4)] !== undefined;
        var baseCol = isAppStd ? c.slice(0, -4) : c;
        var tag = r.cell_changes[baseCol];
        var oldVal = r.before[baseCol] !== undefined ? String(r.before[baseCol]) : "";
        var newVal = r.after[c] !== undefined ? String(r.after[c]) : "";
        if (tag && tag !== "unchanged" && oldVal !== newVal) {
          if (oldVal) { td.appendChild(el("span", oldVal, "diff-old")); }
          td.appendChild(el("span", newVal || "(blank)", "diff-new"));
          var pillCls = tag === "cleared" ? "warn" : (tag === "invalid" ? "bad" : (tag === "healed" || tag === "rescued" ? "heal" : "ok"));
          td.appendChild(document.createTextNode(" "));
          td.appendChild(el("span", tag.toUpperCase(), "pill " + pillCls));
        } else {
          td.textContent = newVal;
        }
        tr.appendChild(td);
      });
      tr.appendChild(el("td", (r.cross_healing_actions || []).join(", "), "muted mono"));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
  }

  function renderMatchScorecard(sc) {
    renderKpis($("match-kpi-strip"), [
      ["Left Matched", sc.matched_left + " / " + sc.total_left + " (" + sc.matched_left_pct + "%)"],
      ["Right Matched", sc.matched_right + " / " + sc.total_right + " (" + sc.matched_right_pct + "%)"],
      ["Active Pairs", sc.matched_pairs],
      ["Potential Queue", sc.potential_pairs],
      ["Unmatched Left", sc.unmatched_left],
      ["Unmatched Right", sc.unmatched_right],
      ["1:1 / N:1 / 1:N / M:N", (sc.cardinality_counts["1:1"] || 0) + " / " + (sc.cardinality_counts["N:1"] || 0) + " / " + (sc.cardinality_counts["1:N"] || 0) + " / " + (sc.cardinality_counts["M:N"] || 0)],
      ["Avg Agreement", sc.avg_attribute_agreement_pct + "%"]
    ]);
  }

  function openPairDrawer(pair) {
    state.selectedPair = pair;
    $("match-detail-drawer").hidden = false;
    $("drawer-title").textContent = pair.pair_id + " — " + pair.effective_status + " (" + pair.score_100 + "/100)";
    $("drawer-expl").textContent = pair.explanation;
    $("steward-note-input").value = pair.steward_note || "";

    var tblWrap = $("drawer-compare-table");
    clear(tblWrap);
    var table = el("table");
    var thead = el("thead");
    var hr = el("tr");
    ["Field", "Left Standardized", "Right Standardized", "Match"].forEach(function (h) { hr.appendChild(el("th", h)); });
    thead.appendChild(hr);
    table.appendChild(thead);
    var tbody = el("tbody");
    [
      ["Organization", "organization", "cmp_org"],
      ["Person", "person_name", "cmp_person"],
      ["FINRA CRD", "crd", "cmp_crd"],
      ["Street", "street1", "cmp_street"],
      ["City", "city", "cmp_city"],
      ["State", "state", "cmp_state"],
      ["Postal", "postal_code", "cmp_postal"],
      ["Country", "country", "cmp_country"],
      ["Phone", "phone", "cmp_phone"],
      ["Email", "email", "cmp_email"],
      ["Website", "website", "cmp_website"],
      ["Roster Members", "roster_count", "cmp_roster"]
    ].forEach(function (spec) {
      var tr = el("tr");
      tr.appendChild(el("th", spec[0]));
      tr.appendChild(el("td", pair.left_display[spec[1]] || "", "mono"));
      tr.appendChild(el("td", pair.right_display[spec[1]] || "", "mono"));
      var status = pair[spec[2]] || "";
      var cls = (status === "EXACT" || status === "EQUIV") ? "ok" : (status === "CONFLICT" ? "bad" : "");
      var td = el("td");
      td.appendChild(el("span", status, "pill " + cls));
      tr.appendChild(td);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    tblWrap.appendChild(table);
  }

  function loadMatchPairs() {
    if (!state.matchJobId) { return; }
    var limit = 200;
    var params = new URLSearchParams({
      view: $("match-view").value,
      cardinality: $("match-card-filter").value,
      search: $("match-search").value.trim(),
      discrepancy_only: $("match-disc-only").checked ? "true" : "false",
      offset: String(state.matchOffset),
      limit: String(limit)
    });
    apiFetch("/ui/api/match/" + state.matchJobId + "/pairs?" + params.toString())
      .then(function (data) {
        renderMatchScorecard(data.scorecard);
        var wrap = $("match-pairs-wrap");
        clear(wrap);
        if (!data.items.length) {
          wrap.appendChild(el("p", "No records match the active filter.", "muted"));
          renderPager("match-pager", 0, 0, 0, limit, function () {});
          return;
        }
        var isUnmatched = params.get("view").indexOf("unmatched_") === 0;
        var table = el("table");
        var thead = el("thead");
        var hr = el("tr");
        var cols = isUnmatched
          ? ["Record ID", "Organization", "Person", "City/State", "Phone", "Email"]
          : ["Pair", "Status", "Score", "Card.", "Left Entity", "Right Entity", "Discrepancies"];
        cols.forEach(function (h) { hr.appendChild(el("th", h)); });
        thead.appendChild(hr);
        table.appendChild(thead);

        var tbody = el("tbody");
        data.items.forEach(function (item) {
          var tr = el("tr");
          if (isUnmatched) {
            tr.appendChild(el("td", item.record_id, "mono"));
            tr.appendChild(el("td", item.organization || ""));
            tr.appendChild(el("td", item.person_name || ""));
            tr.appendChild(el("td", [item.city, item.state].filter(Boolean).join(", ")));
            tr.appendChild(el("td", item.phone || "", "mono"));
            tr.appendChild(el("td", item.email || "", "mono"));
          } else {
            tr.appendChild(el("td", item.pair_id, "mono"));
            var stTd = el("td");
            var stCls = item.effective_status === "MATCHED" ? "ok" : (item.effective_status === "POTENTIAL_MATCH" ? "warn" : "bad");
            stTd.appendChild(el("span", item.effective_status, "pill " + stCls));
            tr.appendChild(stTd);
            tr.appendChild(el("td", item.score_100, "mono"));
            tr.appendChild(el("td", item.cardinality, "mono"));
            tr.appendChild(el("td", item.left_display.organization || item.left_display.person_name || item.left_id));
            tr.appendChild(el("td", item.right_display.organization || item.right_display.person_name || item.right_id));
            tr.appendChild(el("td", (item.discrepancy_fields || []).join(", "), "muted mono"));
            tr.style.cursor = "pointer";
            tr.addEventListener("click", function () { openPairDrawer(item); });
          }
          tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        wrap.appendChild(table);
        renderPager("match-pager", data.offset, data.items.length, data.total, data.limit, function (nextOff) {
          state.matchOffset = nextOff;
          loadMatchPairs();
        });
      }).catch(function (err) { setStatus(err.message, "err"); });
  }

  function sendDecision(decision) {
    if (!state.matchJobId || !state.selectedPair) { return; }
    apiFetch("/ui/api/match/" + state.matchJobId + "/decision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pair_id: state.selectedPair.pair_id,
        decision: decision,
        note: $("steward-note-input").value.trim()
      })
    }).then(function (data) {
      openPairDrawer(data.pair);
      loadMatchPairs();
      setStatus("Updated " + data.pair.pair_id + " -> " + decision, "ok");
    }).catch(function (err) { setStatus(err.message, "err"); });
  }

  function renderDedupClusters(clusters, summary, total) {
    $("dedup-results-card").hidden = false;
    renderKpis($("dedup-kpi-strip"), [
      ["Total Records", summary.total_records],
      ["Clusters", summary.cluster_count],
      ["Multi-Record Clusters", summary.multi_record_clusters],
      ["Duplicates Collapsed", summary.duplicate_rows_collapsed],
      ["Runtime (ms)", summary.elapsed_ms]
    ]);
    var list = $("dedup-cluster-list");
    clear(list);
    var detail = $("dedup-cluster-detail");
    clear(detail);
    detail.appendChild(el("p", "Select a cluster to inspect golden record survivorship.", "muted"));

    function selectCluster(cl, li) {
      document.querySelectorAll("#dedup-cluster-list li").forEach(function (n) { n.classList.remove("selected"); });
      li.classList.add("selected");
      clear(detail);
      detail.appendChild(el("h3", cl.cluster_id + " — Golden: " + cl.golden_record_id));
      detail.appendChild(el("p", "Linkage: " + (cl.reasons || []).join(", "), "muted mono"));
      var tbl = el("table");
      var th = el("tr");
      ["Role", "ID", "Organization", "Person", "Phone", "Action"].forEach(function (h) { th.appendChild(el("th", h)); });
      tbl.appendChild(th);
      cl.members.forEach(function (m) {
        var tr = el("tr");
        tr.appendChild(el("td", m.excluded ? "EXCLUDED" : (m.is_golden ? "GOLDEN" : "MEMBER"), "mono"));
        tr.appendChild(el("td", m.record_id, "mono"));
        tr.appendChild(el("td", m.display.organization || ""));
        tr.appendChild(el("td", m.display.person_name || ""));
        tr.appendChild(el("td", m.display.phone || "", "mono"));
        var actTd = el("td");
        if (cl.cluster_size > 1 || m.excluded) {
          var btn = el("button", m.excluded ? "Restore" : "Exclude", "btn-secondary");
          btn.type = "button";
          btn.addEventListener("click", function () {
            state.dedup.selectedRowIndex = m.row_index;
            apiFetch("/ui/api/dedup/" + state.dedup.jobId + "/override", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ row_index: m.row_index, excluded: !m.excluded })
            }).then(function () { refreshDedupClusters(); })
              .catch(function (err) { setStatus(err.message, "err"); });
          });
          actTd.appendChild(btn);
        }
        tr.appendChild(actTd);
        tbl.appendChild(tr);
      });
      detail.appendChild(tbl);
    }

    clusters.forEach(function (cl) {
      var li = el("li");
      li.appendChild(el("div", cl.cluster_id + " (" + cl.cluster_size + " records)", "mono"));
      var g = cl.golden_display || {};
      li.appendChild(el("div", [g.organization, g.person_name, g.phone].filter(Boolean).join(" • ") || cl.golden_record_id, "muted"));
      li.addEventListener("click", function () {
        state.dedup.selectedRowIndex = cl.golden_row_index;
        selectCluster(cl, li);
      });
      list.appendChild(li);
      if (state.dedup.selectedRowIndex !== null && cl.members.some(function (m) { return m.row_index === state.dedup.selectedRowIndex; })) {
        selectCluster(cl, li);
      }
    });

    renderPager("dedup-pager", state.dedup.offset, clusters.length, total !== undefined ? total : summary.cluster_count, 100, function (nextOff) {
      state.dedup.offset = nextOff;
      refreshDedupClusters();
    });
  }

  function refreshDedupClusters() {
    if (!state.dedup.jobId) { return; }
    var multi = $("dedup-multi-only").checked ? "true" : "false";
    apiFetch("/ui/api/dedup/" + state.dedup.jobId + "/clusters?multi_only=" + multi + "&offset=" + state.dedup.offset + "&limit=100")
      .then(function (data) { renderDedupClusters(data.clusters, data.summary, data.total); })
      .catch(function (err) { setStatus(err.message, "err"); });
  }

  function refreshPresets() {
    apiFetch("/ui/api/presets").then(function (data) {
      var sel = $("preset-select");
      clear(sel);
      sel.appendChild(el("option", "-- Presets --"));
      (data.presets || []).forEach(function (p) {
        var opt = el("option", p.name + " (" + p.mapping_count + " cols)");
        opt.value = p.name;
        sel.appendChild(opt);
      });
    }).catch(function () {});
  }

  function buildLiveForms() {
    [["live-form-a", "a"], ["live-form-b", "b"]].forEach(function (pair) {
      var box = $(pair[0]);
      var pfx = pair[1];
      LIVE_FIELDS.forEach(function (f) {
        var lbl = el("label", f[1]);
        var inp = document.createElement("input");
        inp.type = "text";
        inp.id = "live-" + pfx + "-" + f[0];
        lbl.appendChild(inp);
        box.appendChild(lbl);
      });
    });
  }

  function readLiveForm(pfx) {
    var payload = {};
    LIVE_FIELDS.forEach(function (f) {
      var val = $("live-" + pfx + "-" + f[0]).value.trim();
      if (val) { payload[f[0]] = val; }
    });
    return payload;
  }

  function initTabs() {
    document.querySelectorAll(".tab").forEach(function (btn) {
      btn.addEventListener("click", function () {
        document.querySelectorAll(".tab").forEach(function (b) { b.classList.remove("active"); });
        document.querySelectorAll(".tab-panel").forEach(function (p) { p.classList.remove("active"); });
        btn.classList.add("active");
        state.activeTab = btn.getAttribute("data-tab") || "standardize";
        $("tab-" + state.activeTab).classList.add("active");
      });
    });
  }

  function activeMapperTarget() {
    if (state.activeTab === "dedup") { return { stateObj: state.dedup, slotId: "dedup-mapper-slot" }; }
    if (state.activeTab === "match") { return { stateObj: state.matchLeft, slotId: "match-left-mapper" }; }
    return { stateObj: state.std, slotId: "std-mapper-slot" };
  }

  function initEvents() {
    $("std-preview-btn").addEventListener("click", function () {
      if (!state.std.source) { return; }
      setStatus("Generating dry-run preview...");
      apiFetch("/ui/api/standardize/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_id: state.std.source.source_id,
          mapping_config: state.std.mapping,
          options: gatherStdOptions(),
          limit: 50
        })
      }).then(function (data) {
        renderStdPreview(data);
        setStatus("Preview ready (" + data.cells_changed + " changes across " + data.preview_count + " rows)", "ok");
      }).catch(function (err) { setStatus(err.message, "err"); });
    });

    $("std-run-btn").addEventListener("click", function () {
      if (!state.std.source) { return; }
      setStatus("Standardizing full file...");
      var outPath = $("std-output-path").value.trim() || null;
      apiFetch("/ui/api/standardize/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_id: state.std.source.source_id,
          mapping_config: state.std.mapping,
          options: gatherStdOptions(),
          output_path: outPath
        })
      }).then(function (data) {
        $("std-results-card").hidden = false;
        renderKpis($("std-kpi-strip"), [
          ["Input Rows", data.input_rows],
          ["Output Rows", data.output_rows],
          ["Modified Rows", data.modified_rows],
          ["Cells Changed", data.cells_changed],
          ["Cells Cleared", data.cells_cleared],
          ["Elapsed (ms)", data.elapsed_ms]
        ]);
        var dlSlot = $("std-download-slot");
        clear(dlSlot);
        var dlBtn = el("button", "Download " + data.download_filename, "btn-ok");
        dlBtn.type = "button";
        dlBtn.addEventListener("click", function () { downloadFile(data.download_url, data.download_filename); });
        dlSlot.appendChild(dlBtn);
        if (!outPath) {
          downloadFile(data.download_url, data.download_filename);
        } else {
          setStatus("Saved standardized output to " + data.output_path, "ok");
        }
      }).catch(function (err) { setStatus(err.message, "err"); });
    });

    $("match-profile").addEventListener("change", function () {
      var thr = PROFILE_DEFAULTS[$("match-profile").value] || [0.70, 0.50];
      $("match-threshold").value = thr[0].toFixed(2);
      $("match-potential-threshold").value = thr[1].toFixed(2);
    });

    $("match-run-btn").addEventListener("click", function () {
      if (!state.matchLeft.source || !state.matchRight.source) {
        setStatus("Load both Left and Right datasets before matching.", "err");
        return;
      }
      setStatus("Running cross-system blocking & multi-signal scoring...");
      var buildRoster = function (rosterState, parentId, colsId) {
        if (!rosterState.source || !$(parentId).value) { return null; }
        var cols = $(colsId).value.split(",").map(function (c) { return c.trim(); }).filter(Boolean);
        return cols.length ? { source_id: rosterState.source.source_id, parent_id_col: $(parentId).value, member_cols: cols } : null;
      };
      apiFetch("/ui/api/match/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          left_source_id: state.matchLeft.source.source_id,
          right_source_id: state.matchRight.source.source_id,
          left_mapping: state.matchLeft.mapping,
          right_mapping: state.matchRight.mapping,
          options: gatherMatchingOptions(),
          left_roster: buildRoster(state.leftRoster, "left-roster-parent", "left-roster-cols"),
          right_roster: buildRoster(state.rightRoster, "right-roster-parent", "right-roster-cols")
        })
      }).then(function (data) {
        state.matchJobId = data.job_id;
        state.matchOffset = 0;
        $("match-results-card").hidden = false;
        $("match-detail-drawer").hidden = true;
        renderMatchScorecard(data.scorecard);
        loadMatchPairs();
        setStatus("Matching complete (" + data.scorecard.matched_pairs + " matched, " + data.scorecard.potential_pairs + " potential)", "ok");
      }).catch(function (err) { setStatus(err.message, "err"); });
    });

    var resetMatchAndLoad = function () { state.matchOffset = 0; loadMatchPairs(); };
    $("match-refresh-btn").addEventListener("click", resetMatchAndLoad);
    $("match-search").addEventListener("keydown", function (e) { if (e.key === "Enter") { resetMatchAndLoad(); } });
    $("match-search").addEventListener("search", resetMatchAndLoad);
    $("match-view").addEventListener("change", resetMatchAndLoad);
    $("match-card-filter").addEventListener("change", resetMatchAndLoad);
    $("match-disc-only").addEventListener("change", resetMatchAndLoad);
    $("steward-approve-btn").addEventListener("click", function () { sendDecision("approve"); });
    $("steward-reject-btn").addEventListener("click", function () { sendDecision("reject"); });
    $("steward-reset-btn").addEventListener("click", function () { sendDecision("reset"); });

    document.querySelectorAll(".match-exp-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (!state.matchJobId) { return; }
        var art = btn.getAttribute("data-art");
        var fmt = $("match-export-fmt").value;
        var url = "/ui/api/match/" + state.matchJobId + "/export?artifact=" + encodeURIComponent(art) + "&format=" + encodeURIComponent(fmt);
        downloadFile(url, art + "." + fmt);
      });
    });

    $("dedup-profile").addEventListener("change", function () {
      var thr = PROFILE_DEFAULTS[$("dedup-profile").value] || [0.70, 0.50];
      $("dedup-threshold").value = thr[0].toFixed(2);
    });

    $("dedup-run-btn").addEventListener("click", function () {
      if (!state.dedup.source) { return; }
      setStatus("Clustering duplicate records...");
      apiFetch("/ui/api/dedup/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_id: state.dedup.source.source_id,
          mapping_config: state.dedup.mapping,
          options: gatherMatchingOptions()
        })
      }).then(function (data) {
        state.dedup.jobId = data.job_id;
        state.dedup.offset = 0;
        state.dedup.selectedRowIndex = null;
        $("dedup-export-btn").disabled = false;
        renderDedupClusters(data.clusters, data.summary, data.summary.cluster_count);
        setStatus("Found " + data.summary.cluster_count + " clusters", "ok");
      }).catch(function (err) { setStatus(err.message, "err"); });
    });

    $("dedup-multi-only").addEventListener("change", function () {
      state.dedup.offset = 0;
      refreshDedupClusters();
    });
    $("dedup-export-btn").addEventListener("click", function () {
      if (!state.dedup.jobId) { return; }
      var mode = $("dedup-export-mode").value;
      downloadFile("/ui/api/dedup/" + state.dedup.jobId + "/export?mode=" + encodeURIComponent(mode), "deduplicated_" + mode + ".csv");
    });

    $("preset-save-btn").addEventListener("click", function () {
      var name = window.prompt("Preset name (letters, digits, spaces, '-', '_'):");
      if (!name) { return; }
      var active = activeMapperTarget();
      apiFetch("/ui/api/presets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name,
          mapping_config: active.stateObj.mapping,
          standardize_options: gatherStdOptions(),
          matching_options: gatherMatchingOptions()
        })
      }).then(function () { refreshPresets(); setStatus("Saved preset " + name, "ok"); })
        .catch(function (err) { setStatus(err.message, "err"); });
    });

    $("preset-load-btn").addEventListener("click", function () {
      var name = $("preset-select").value;
      if (!name) { return; }
      var active = activeMapperTarget();
      apiFetch("/ui/api/presets/" + encodeURIComponent(name)).then(function (p) {
        if (p.mapping_config && p.mapping_config.mappings) {
          var allowed = active.stateObj.source ? active.stateObj.source.columns : null;
          var nextMappings = allowed
            ? p.mapping_config.mappings.filter(function (m) { return allowed.indexOf(m.column) !== -1; })
            : p.mapping_config.mappings;
          active.stateObj.mapping = {
            mappings: nextMappings,
            group_cross_healing: p.mapping_config.group_cross_healing || {}
          };
          if (active.stateObj.source) { renderMapper(active.slotId, active.stateObj); }
        }
        applyStdOptions(p.standardize_options);
        applyMatchingOptions(p.matching_options);
        setStatus("Loaded preset " + name, "ok");
      }).catch(function (err) { setStatus(err.message, "err"); });
    });

    $("preset-del-btn").addEventListener("click", function () {
      var name = $("preset-select").value;
      if (!name) { return; }
      apiFetch("/ui/api/presets/" + encodeURIComponent(name), { method: "DELETE" })
        .then(function () { refreshPresets(); setStatus("Deleted preset " + name, "ok"); })
        .catch(function (err) { setStatus(err.message, "err"); });
    });

    $("live-mode").addEventListener("change", function () {
      $("live-form-b").hidden = $("live-mode").value !== "compare";
    });
    $("live-sample-btn").addEventListener("click", function () {
      $("live-a-organization").value = "The Acme Holdings, Inc. /DE/ (DBA Acme Cloud)";
      $("live-a-person_name").value = "Smith, Jr., Dr. Bob J., MD";
      $("live-a-street1").value = "350 Fifth Ave Tel: 555-2368";
      $("live-a-city").value = "New York";
      $("live-a-postal_code").value = "10118";
      $("live-a-email").value = "Bob.Smith+crm@gmial.com";
      $("live-a-website").value = "http://www.acme.com/?utm_source=linkedin";
      $("live-b-organization").value = "ACME HOLDINGS INC";
      $("live-b-person_name").value = "Robert J Smith Jr";
      $("live-b-street1").value = "350 5th Ave";
      $("live-b-city").value = "New York";
      $("live-b-state").value = "NY";
      $("live-b-postal_code").value = "10118";
      $("live-b-phone").value = "+1-212-555-2368";
    });
    $("live-run-btn").addEventListener("click", function () {
      var mode = $("live-mode").value;
      apiFetch("/ui/api/live/inspect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: mode,
          entity_a: readLiveForm("a"),
          entity_b: mode === "compare" ? readLiveForm("b") : null
        })
      }).then(function (data) { $("live-output").textContent = JSON.stringify(data, null, 2); })
        .catch(function (err) { setStatus(err.message, "err"); });
    });
  }

  function populateRosterCols(selId, cols) {
    var sel = $(selId);
    clear(sel);
    cols.forEach(function (c) {
      var o = el("option", c);
      o.value = c;
      sel.appendChild(o);
    });
  }

  function init() {
    initTabs();
    buildLiveForms();
    apiFetch("/ui/api/capabilities").then(function (caps) {
      state.capabilities = caps;
      $("runtime-badge").textContent = "v" + caps.version + (caps.native_available ? " • Rust PyO3 Active" : " • Pure Python");
      $("std-local-out-wrap").hidden = !caps.local_paths_enabled;

      var sigBox = $("match-signals-box");
      sigBox.appendChild(el("span", "Enabled Signals:", "muted"));
      caps.signals.forEach(function (sig) {
        var lbl = el("label");
        var cb = document.createElement("input");
        cb.type = "checkbox";
        cb.className = "match-sig-cb";
        cb.value = sig;
        cb.checked = true;
        lbl.appendChild(cb);
        lbl.appendChild(document.createTextNode(sig));
        sigBox.appendChild(lbl);
      });

      buildSourceWidget("std-source-slot", function (data) {
        state.std.source = data;
        state.std.suggested = data.suggested_mapping;
        state.std.mapping = JSON.parse(JSON.stringify(data.suggested_mapping));
        $("std-mapper-card").hidden = false;
        $("std-options-card").hidden = false;
        $("std-results-card").hidden = true;
        clear($("std-download-slot"));
        clear($("std-preview-wrap"));
        clear($("std-kpi-strip"));
        renderMapper("std-mapper-slot", state.std);
      }, false);

      buildSourceWidget("match-left-source", function (data) {
        state.matchLeft.source = data;
        state.matchLeft.suggested = data.suggested_mapping;
        state.matchLeft.mapping = JSON.parse(JSON.stringify(data.suggested_mapping));
        state.matchJobId = null;
        state.matchOffset = 0;
        $("match-results-card").hidden = true;
        $("match-detail-drawer").hidden = true;
        renderMapper("match-left-mapper", state.matchLeft);
      }, false);

      buildSourceWidget("match-right-source", function (data) {
        state.matchRight.source = data;
        state.matchRight.suggested = data.suggested_mapping;
        state.matchRight.mapping = JSON.parse(JSON.stringify(data.suggested_mapping));
        state.matchJobId = null;
        state.matchOffset = 0;
        $("match-results-card").hidden = true;
        $("match-detail-drawer").hidden = true;
        renderMapper("match-right-mapper", state.matchRight);
      }, false);

      buildSourceWidget("match-left-roster-source", function (data) {
        state.leftRoster.source = data;
        populateRosterCols("left-roster-parent", data.columns);
      }, true);

      buildSourceWidget("match-right-roster-source", function (data) {
        state.rightRoster.source = data;
        populateRosterCols("right-roster-parent", data.columns);
      }, true);

      buildSourceWidget("dedup-source-slot", function (data) {
        state.dedup.source = data;
        state.dedup.suggested = data.suggested_mapping;
        state.dedup.mapping = JSON.parse(JSON.stringify(data.suggested_mapping));
        state.dedup.jobId = null;
        state.dedup.offset = 0;
        state.dedup.selectedRowIndex = null;
        $("dedup-mapper-card").hidden = false;
        $("dedup-results-card").hidden = true;
        $("dedup-export-btn").disabled = true;
        renderMapper("dedup-mapper-slot", state.dedup);
      }, false);

      initEvents();
      refreshPresets();
      setStatus("Ready", "ok");
    }).catch(function (err) { setStatus("Failed to load capabilities: " + err.message, "err"); });
  }

  init();
})();
