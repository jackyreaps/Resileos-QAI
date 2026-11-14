/* Admin console: Reports, Knowledge, Operator, Diagnostics.
 * The page checks /api/session/me for admin, but that is only a courtesy:
 * the Pages proxy refuses every admin endpoint for non-admin accounts
 * (see functions/_admin.js). Nothing here changes how facts are saved;
 * every save still goes through the server's Eat checks. */
(function () {
  "use strict";
  var API = "/api/session/v1";
  var csrf = "";
  var TABS = [
    ["reports", "/admin/reports", "Reports"],
    ["knowledge", "/admin/knowledge", "Knowledge"],
    ["operator", "/admin/operator", "Operator"],
    ["diagnostics", "/admin/diagnostics", "Diagnostics"],
  ];

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function hubId() {
    try { return localStorage.getItem("resileos_hub_id") || "anon"; } catch (err) { return "anon"; }
  }

  function renderTabs(active) {
    var mount = $("admin-tabs");
    if (!mount) return;
    mount.replaceChildren();
    TABS.forEach(function (tab) {
      var a = el("a", "admin-tab", tab[2]);
      a.href = tab[1];
      if (tab[0] === active) a.setAttribute("aria-current", "page");
      mount.appendChild(a);
    });
  }

  async function call(method, path, body) {
    var headers = {};
    if (body !== undefined && body !== null) headers["content-type"] = "application/json";
    if (csrf) headers["x-csrf-token"] = csrf;
    var res = await fetch(API + path, {
      method: method,
      credentials: "same-origin",
      headers: headers,
      body: body !== undefined && body !== null ? JSON.stringify(body) : undefined,
    });
    var text = await res.text();
    var data;
    try { data = text ? JSON.parse(text) : {}; } catch (err) { data = { detail: text.slice(0, 400) }; }
    return { status: res.status, ok: res.ok, data: data };
  }

  function summarize(result) {
    var d = result.data || {};
    if (!result.ok) {
      var detail = typeof d.detail === "string" ? d.detail : (d.detail && d.detail.reason) || "";
      return "Didn't work (" + result.status + "). " + (detail || "See the raw response below.");
    }
    if (Array.isArray(d.decisions)) {
      var saved = Number(d.learned || 0);
      return "Found " + d.decisions.length + " possible fact" + (d.decisions.length === 1 ? "" : "s") + ". "
        + (saved ? "Saved " + saved + "." : "Nothing was saved.");
    }
    if (Array.isArray(d.checkpoints)) return d.checkpoints.length + " checkpoint" + (d.checkpoints.length === 1 ? "" : "s") + ".";
    if (Array.isArray(d.rows)) return d.rows.length + " saved row" + (d.rows.length === 1 ? "" : "s") + ".";
    if (typeof d.value === "string" && d.value) return d.value;
    if (typeof d.answer === "string" && d.answer) return d.answer;
    if (d.status) return "Status: " + d.status + (d.detail && typeof d.detail === "string" ? ". " + d.detail : "");
    return "Done.";
  }

  function showResult(out, result) {
    out.replaceChildren();
    out.hidden = false;
    out.appendChild(el("p", "admin-summary" + (result.ok ? "" : " err"), summarize(result)));
    var fold = el("details", "admin-raw");
    fold.appendChild(el("summary", "", "Raw response"));
    fold.appendChild(el("pre", "", JSON.stringify(result.data, null, 2)));
    out.appendChild(fold);
  }

  /* A tool card with plain fields. spec: {title, explain, fields, button, run(values) -> {method, path, body}} */
  function toolCard(spec) {
    var card = el("div", "card admin-card");
    card.appendChild(el("h3", "", spec.title));
    if (spec.explain) card.appendChild(el("p", "admin-explain", spec.explain));
    var form = el("form", "form admin-form");
    var inputs = {};
    (spec.fields || []).forEach(function (f) {
      var id = "f-" + Math.random().toString(36).slice(2, 9);
      var input;
      if (f.type === "checkbox") {
        var wrap = el("label", "admin-check");
        input = el("input");
        input.type = "checkbox";
        input.id = id;
        input.checked = Boolean(f.value);
        wrap.append(input, document.createTextNode(" " + f.label));
        form.appendChild(wrap);
      } else {
        var label = el("label", "", f.label);
        label.htmlFor = id;
        form.appendChild(label);
        input = el(f.type === "textarea" || f.type === "json" ? "textarea" : "input");
        input.id = id;
        if (f.type === "json") {
          input.spellcheck = false;
          input.className = "mono";
          input.rows = 6;
          input.value = typeof f.value === "string" ? f.value : JSON.stringify(f.value || {}, null, 2);
        } else {
          if (f.type === "textarea") input.rows = 5;
          input.value = f.value || "";
          if (f.placeholder) input.placeholder = f.placeholder;
        }
        form.appendChild(input);
      }
      if (f.help) form.appendChild(el("p", "micro", f.help));
      inputs[f.name] = { node: input, type: f.type };
    });
    var row = el("div", "cta-row");
    var btn = el("button", "btn btn-ghost", spec.button || "Run");
    btn.type = "submit";
    row.appendChild(btn);
    form.appendChild(row);
    var out = el("div", "admin-out");
    out.hidden = true;
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      var values = {};
      try {
        Object.keys(inputs).forEach(function (name) {
          var item = inputs[name];
          if (item.type === "checkbox") values[name] = item.node.checked;
          else if (item.type === "json") values[name] = item.node.value.trim() ? JSON.parse(item.node.value) : {};
          else values[name] = item.node.value.trim();
        });
      } catch (err) {
        showResult(out, { ok: false, status: "input", data: { detail: "The request isn't valid JSON: " + err.message } });
        return;
      }
      var req = spec.run(values);
      if (!req) return;
      if (req.error) {
        showResult(out, { ok: false, status: "input", data: { detail: req.error } });
        return;
      }
      btn.disabled = true;
      try {
        var result = await call(req.method, req.path, req.body);
        showResult(out, result);
        if (spec.after) spec.after(result, out);
      } catch (err) {
        showResult(out, { ok: false, status: "network", data: { detail: "Couldn't reach the server." } });
      } finally {
        btn.disabled = false;
      }
    });
    card.append(form, out);
    return card;
  }

  function group(mount, title, intro) {
    var section = el("div", "admin-group");
    section.appendChild(el("h2", "", title));
    if (intro) section.appendChild(el("p", "admin-intro", intro));
    var grid = el("div", "admin-grid");
    section.appendChild(grid);
    mount.appendChild(section);
    return grid;
  }

  // ---------- Knowledge: Add facts ----------
  var ACCEPT = [".txt", ".md", ".csv", ".json", ".lean"];
  function extOf(name) { var m = /\.[^.]+$/.exec(String(name || "").toLowerCase()); return m ? m[0] : ".txt"; }

  function addFactsPanel() {
    var section = el("div", "admin-group add-facts");
    section.appendChild(el("h2", "", "Add facts"));
    section.appendChild(el("p", "admin-intro",
      "Drop files or paste some text. Each line like \u201cAthens | capital_of | Greece\u201d becomes a fact; a Lean proof that checks becomes a fact too. You'll see what would be saved before anything is."));
    var card = el("div", "card admin-card");
    var drop = el("div", "drop-zone");
    drop.tabIndex = 0;
    drop.setAttribute("role", "button");
    drop.appendChild(el("strong", "", "Drop files here"));
    drop.appendChild(el("span", "micro", " or click to choose. Text, Markdown, CSV, JSON, or Lean."));
    var picker = el("input");
    picker.type = "file";
    picker.multiple = true;
    picker.accept = ACCEPT.join(",");
    picker.hidden = true;
    var chosen = el("ul", "chosen-files");
    var paste = el("textarea", "paste-box");
    paste.rows = 5;
    paste.placeholder = "Or paste here, one fact per line:\nAthens | capital_of | Greece | 1834-01-01\nLisbon | capital_of | Portugal";
    paste.setAttribute("aria-label", "Paste facts");
    var mineRow = el("div", "cta-row");
    var mineBtn = el("button", "btn btn-ghost", "Use from My files");
    mineBtn.type = "button";
    var mineList = el("div", "mine-list");
    mineList.hidden = true;
    mineRow.append(mineBtn);
    var actions = el("div", "cta-row");
    var checkBtn = el("button", "btn", "Check facts");
    checkBtn.type = "button";
    actions.appendChild(checkBtn);
    var out = el("div", "admin-out");
    out.hidden = true;
    card.append(drop, picker, chosen, paste, mineRow, mineList, actions, out);
    section.appendChild(card);

    var items = [];
    function showChosen() {
      chosen.replaceChildren();
      items.forEach(function (it, i) {
        var li = el("li", "", it.name + " ");
        var x = el("button", "btn-link", "remove");
        x.type = "button";
        x.addEventListener("click", function () { items.splice(i, 1); showChosen(); });
        li.appendChild(x);
        chosen.appendChild(li);
      });
    }
    function addFiles(list) {
      Array.prototype.forEach.call(list || [], function (file) {
        if (ACCEPT.indexOf(extOf(file.name)) === -1) {
          items.push({ name: file.name, text: "" });
          showChosen();
          return;
        }
        file.text().then(function (text) { items.push({ name: file.name, text: text }); showChosen(); });
      });
    }
    drop.addEventListener("click", function () { picker.click(); });
    drop.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); picker.click(); } });
    picker.addEventListener("change", function () { addFiles(picker.files); picker.value = ""; });
    ["dragenter", "dragover"].forEach(function (t) { drop.addEventListener(t, function (e) { e.preventDefault(); drop.classList.add("over"); }); });
    ["dragleave", "drop"].forEach(function (t) { drop.addEventListener(t, function (e) { e.preventDefault(); drop.classList.remove("over"); }); });
    drop.addEventListener("drop", function (e) { addFiles(e.dataTransfer && e.dataTransfer.files); });

    mineBtn.addEventListener("click", async function () {
      mineList.hidden = false;
      mineList.replaceChildren(el("p", "micro", "Loading your files\u2026"));
      var res = await call("GET", "/files");
      mineList.replaceChildren();
      var files = ((res.data || {}).files || []).filter(function (f) { return ACCEPT.indexOf(extOf(f.name)) !== -1; });
      if (!res.ok || !files.length) { mineList.appendChild(el("p", "micro", res.ok ? "No text, CSV, JSON, or Lean files in My files yet." : "Couldn't load My files.")); return; }
      files.forEach(function (f) {
        var b = el("button", "btn btn-ghost btn-sm", f.name);
        b.type = "button";
        b.addEventListener("click", async function () {
          var r = await fetch(API + "/files/" + encodeURIComponent(f.id), { credentials: "same-origin" });
          if (r.ok) { items.push({ name: f.name, text: await r.text() }); showChosen(); }
        });
        mineList.appendChild(b);
      });
    });

    function factLine(f) {
      var when = f.valid_from || f.valid_to ? " (" + (f.valid_from || "\u2026") + " to " + (f.valid_to || "\u2026") + ")" : "";
      return f.subject + " \u00b7 " + f.relation + " \u00b7 " + f.obj + when;
    }

    checkBtn.addEventListener("click", async function () {
      var batch = items.slice();
      if (paste.value.trim()) batch.push({ name: "pasted.txt", text: paste.value });
      if (!batch.length) { out.hidden = false; out.replaceChildren(el("p", "admin-summary err", "Drop a file or paste something first.")); return; }
      checkBtn.disabled = true;
      var res = await call("POST", "/knowledge/preview", { items: batch });
      checkBtn.disabled = false;
      out.hidden = false;
      out.replaceChildren();
      if (!res.ok) { showResult(out, res); return; }
      var ready = [];
      var list = el("ul", "fact-items");
      (res.data.items || []).forEach(function (item) {
        var li = el("li", "fact-item");
        li.appendChild(el("strong", "", item.name + ": "));
        li.appendChild(document.createTextNode(item.status));
        var fold = el("details", "admin-raw");
        fold.appendChild(el("summary", "", "Details"));
        var inner = el("ul", "fact-rows");
        (item.facts || []).forEach(function (f) {
          var row = el("li", "fact-row " + f.action);
          if (f.action === "accept") {
            var box = el("input");
            box.type = "checkbox";
            box.checked = true;
            var fact = { subject: f.subject, relation: f.relation, obj: f.obj, valid_from: f.valid_from, valid_to: f.valid_to, item: item.name };
            ready.push({ box: box, fact: fact });
            var lab = el("label", "");
            lab.append(box, document.createTextNode(" " + factLine(f)));
            row.appendChild(lab);
          } else {
            row.textContent = factLine(f) + " \u2014 " + (f.reason === "overlapping_competing_claim" ? "conflicts with another fact you're adding" : f.action === "conflict" ? "conflicts with an existing fact" : f.reason === "already_stored" ? "already saved" : "held back (" + String(f.reason || f.action).replace(/_/g, " ") + ")");
          }
          inner.appendChild(row);
        });
        if (item.proof) inner.appendChild(el("li", "micro", "Lean: " + item.proof.status + (item.proof.summary ? " \u2014 " + item.proof.summary : "")));
        fold.appendChild(inner);
        li.appendChild(fold);
        list.appendChild(li);
      });
      out.appendChild(list);
      if (!ready.length) { out.appendChild(el("p", "micro", "Nothing is ready to save.")); return; }
      var save = el("button", "btn", "Save " + ready.length + " fact" + (ready.length === 1 ? "" : "s"));
      save.type = "button";
      var saveOut = el("p", "admin-summary");
      save.addEventListener("click", async function () {
        var facts = ready.filter(function (r) { return r.box.checked; }).map(function (r) { return r.fact; });
        if (!facts.length) { saveOut.textContent = "Tick at least one fact."; return; }
        if (!window.confirm("Save " + facts.length + " fact" + (facts.length === 1 ? "" : "s") + "? Each one still goes through the accuracy checks.")) return;
        save.disabled = true;
        var done = await call("POST", "/knowledge/commit", { facts: facts, confirm: true });
        saveOut.textContent = done.ok ? done.data.status : summarize(done);
        saveOut.className = "admin-summary" + (done.ok ? "" : " err");
      });
      var row = el("div", "cta-row");
      row.append(save);
      out.append(row, saveOut);
    });
    return section;
  }

  // ---------- Knowledge ----------
  function knowledgePage(mount) {
    var add = group(mount, "Check and look up facts",
      "Facts are short statements like \u201cAlice works at Acme\u201d. Every fact goes through the same accuracy checks before it is saved. Anything that fails a check is skipped, never forced in.");
    mount.insertBefore(addFactsPanel(), add.parentNode);
    add.appendChild(toolCard({
      title: "Check one fact (doesn't save)",
      explain: "See whether a single fact would pass the checks, and why. Nothing is written.",
      fields: [
        { name: "subject", label: "Who or what", value: "Zeus" },
        { name: "relation", label: "Detail", value: "domain" },
        { name: "obj", label: "Value", value: "sky" },
      ],
      button: "Check it",
      run: function (v) {
        if (!v.subject || !v.relation || !v.obj) return { error: "Fill in all three boxes." };
        return { method: "POST", path: "/eat/preview", body: { claim: { subject: v.subject, relation: v.relation, obj: v.obj }, allow_sys: false } };
      },
    }));
    add.appendChild(toolCard({
      title: "Look up a fact",
      explain: "Ask what is saved for a subject and detail. It says so if nothing is saved.",
      fields: [
        { name: "subject", label: "Who or what", value: "Zeus" },
        { name: "relation", label: "Detail", value: "domain" },
      ],
      button: "Look up",
      run: function (v) {
        if (!v.subject || !v.relation) return { error: "Fill in both boxes." };
        return { method: "POST", path: "/council/query", body: { subject: v.subject, relation: v.relation, profile: "personal" } };
      },
    }));
    add.appendChild(toolCard({
      title: "Find contradictions",
      explain: "Looks through saved facts for ones that disagree with each other. Read-only.",
      fields: [],
      button: "Check now",
      run: function () { return { method: "POST", path: "/tools/residual_consistency", body: {} }; },
    }));

    var memory = group(mount, "Saved memory for one space",
      "Each person or project has its own memory space. Look at what's saved there, change a value, or remove one.");
    memory.appendChild(toolCard({
      title: "See what's saved",
      fields: [{ name: "hub", label: "Space", value: hubId(), help: "\u201canon\u201d is the shared trial space." }],
      button: "Show",
      run: function (v) { return { method: "GET", path: "/hub/" + encodeURIComponent(v.hub || "anon") + "/ledger" }; },
    }));
    memory.appendChild(toolCard({
      title: "Change a saved value",
      fields: [
        { name: "hub", label: "Space", value: hubId() },
        { name: "relation", label: "Detail", value: "prefers" },
        { name: "obj", label: "Current value" },
        { name: "new_obj", label: "New value" },
      ],
      button: "Change",
      run: function (v) {
        if (!v.obj || !v.new_obj) return { error: "Fill in the current and new values." };
        return { method: "PUT", path: "/hub/" + encodeURIComponent(v.hub || "anon") + "/ledger", body: { relation: v.relation, obj: v.obj, new_obj: v.new_obj } };
      },
    }));
    memory.appendChild(toolCard({
      title: "Remove a saved value",
      fields: [
        { name: "hub", label: "Space", value: hubId() },
        { name: "relation", label: "Detail", value: "prefers" },
        { name: "obj", label: "Value to remove" },
      ],
      button: "Remove",
      run: function (v) {
        if (!v.obj) return { error: "Say which value to remove." };
        if (!window.confirm("Remove \u201c" + v.obj + "\u201d from " + (v.hub || "anon") + "?")) return null;
        return { method: "DELETE", path: "/hub/" + encodeURIComponent(v.hub || "anon") + "/ledger?relation=" + encodeURIComponent(v.relation) + "&obj=" + encodeURIComponent(v.obj) };
      },
    }));

    var learning = group(mount, "Learning and checkpoints",
      "A learning cycle reviews recent conversations and saves only the facts that pass the checks. Checkpoints are saved snapshots you can go back to.");
    learning.appendChild(toolCard({
      title: "Run a learning cycle",
      fields: [{ name: "user", label: "Space", value: hubId() }],
      button: "Run cycle",
      run: function (v) { return { method: "POST", path: "/kin/cycle", body: { apply_policy: true, user_id: v.user || hubId() } }; },
    }));
    learning.appendChild(toolCard({
      title: "List checkpoints",
      fields: [],
      button: "List",
      run: function () { return { method: "GET", path: "/kin/hades/list" }; },
    }));
    learning.appendChild(toolCard({
      title: "Go back to a checkpoint",
      explain: "Copy an id from the list above.",
      fields: [{ name: "id", label: "Checkpoint id" }],
      button: "Restore",
      run: function (v) {
        if (!v.id) return { error: "Paste a checkpoint id." };
        if (!window.confirm("Restore checkpoint " + v.id + "?")) return null;
        return { method: "POST", path: "/kin/hades/restore", body: { checkpoint_id: v.id, fresh: true } };
      },
    }));
  }

  // ---------- Diagnostics ----------
  var SAMPLE = [[0, 1], [1, 0]];
  var RAW_TOOLS = [
    ["Studio", [
      ["Make a video (raw)", "POST", "/studio/forge/video", { prompt: "demo", stage: "draft" }],
      ["Clip from frames (raw)", "POST", "/studio/video", { prompt: "demo", stage: "draft", frames: [SAMPLE, SAMPLE] }],
      ["Plan, test, debug", "POST", "/studio/plan-test-debug", { goal: "check status" }],
      ["Stop a running job", "POST", "/studio/stop", { owner: "" }],
      ["List codecs", "GET", "/studio/codecs", null],
      ["Prior report", "GET", "/studio/service/prior", null],
      ["Studio panel", "GET", "/studio/panel", null],
      ["Sampler status", "GET", "/studio/external-sampler", null],
      ["Project codec", "POST", "/studio/codecs/project", { image: SAMPLE, m: 4, n: 4 }],
      ["Register candidate (doesn't learn)", "POST", "/studio/candidates", { kind: "image", path: "candidate://studio-demo", title: "Studio demo", world_id: "studio", note: "" }],
      ["Round-trip", "POST", "/studio/service/round-trip", { image: SAMPLE, codec_name: "pca_component" }],
      ["Sample prior", "POST", "/studio/service/sample", { label: 0, seed: 0, register: false }],
      ["Studio gate", "POST", "/studio/gate", { packet: { id: "studio-demo", budget_remaining: {} } }],
      ["Propose sampler (refused unless enabled)", "POST", "/studio/external-sampler", { condition: { prompt: "demo" }, register: false }],
    ]],
    ["Shared patterns (content-free, read only)", [
      ["Hub pattern aggregate + dream candidates", "GET", "/factors/hub", null],
    ]],
    ["Perception and language (preview only, commit: false)", [
      ["Perceive image", "POST", "/perceive/image", { image: SAMPLE, subject: "image:studio-demo", commit: false }],
      ["Perceive art", "POST", "/perceive/art", { title: "Demo", description: "studio panel", world_id: "world:art", commit: false }],
      ["Perceive frame", "POST", "/perceive/frame", { image: SAMPLE, subject: "frame:studio-demo", commit: false }],
      ["Perceive language", "POST", "/perceive/language", { text: "hello from the studio", subject: "text", commit: false }],
      ["Detect language", "POST", "/language/detect", { text: "hello from the studio" }],
      ["Translate", "POST", "/language/translate", { text: "hello", target: "en", source: null }],
      ["Generate fluid", "POST", "/generate/fluid", { belt: 0, frame: 0, persona: "honest", subject: "frame" }],
      ["Generate local pattern", "POST", "/generate/local", { belt: 0, frame: 0, persona: "honest", subject: "frame" }],
    ]],
    ["Reply engine", [
      ["Custom reply from rows", "POST", "/mouth/custom", { rows: [{ subject: "Zeus", relation: "domain", obj: "sky" }], question: "" }],
      ["Explain", "POST", "/explain", { query: "domain", hub_rows: ["sky"] }],
      ["Format a fact line (doesn't learn)", "POST", "/remember", { subject: "demo", relation: "note", obj: "ui" }],
      ["Agent task (read)", "POST", "/agent/task", { goal: "status", steps: [{ tool: "git_status", args: {} }] }],
      ["Agent task (write, should refuse)", "POST", "/agent/task", { goal: "do not write", steps: [{ tool: "write_file", args: { rel: "nope.txt", content: "x" } }] }],
      ["Separated learning cycle", "POST", "/kin/separated_cycle", { writer: "apollo", subject: "world:apollo", facts: [], art: false, use_council: true, use_athena: false, profile: "personal" }],
    ]],
    ["Companion", [
      ["Add a like", "POST", "/aphrodite/{hub}/preference", { topic: "tea", like: true, care: 1 }],
      ["Add a dislike", "POST", "/aphrodite/{hub}/preference", { topic: "noise", like: false, care: 1 }],
      ["Reset companion", "POST", "/aphrodite/{hub}/reset", {}],
    ]],
  ];

  function rawCard(title, method, path, body) {
    var fields = body === null ? [] : [{ name: "body", label: "Request", type: "json", value: body }];
    return toolCard({
      title: title,
      explain: method + " " + path,
      fields: fields,
      button: "Run",
      run: function (v) {
        var real = path.replace("{hub}", encodeURIComponent(hubId()));
        return { method: method, path: real, body: body === null ? undefined : v.body };
      },
    });
  }

  function settingsCard() {
    var card = el("div", "card admin-card");
    card.appendChild(el("h3", "", "This browser"));
    var form = el("div", "form admin-form");
    var debugWrap = el("label", "admin-check");
    var debug = el("input");
    debug.type = "checkbox";
    debug.id = "debug-toggle";
    try { debug.checked = localStorage.getItem("resileos_debug") === "1"; } catch (err) { /* ignore */ }
    debug.addEventListener("change", function () {
      try { localStorage.setItem("resileos_debug", debug.checked ? "1" : "0"); } catch (err) { /* ignore */ }
      note.textContent = debug.checked ? "Chat replies now show a Details fold in this browser." : "Technical details are hidden in chat.";
    });
    debugWrap.append(debug, document.createTextNode(" Show technical details under chat replies"));
    var hubLabel = el("label", "", "Memory space for chat in this browser");
    hubLabel.htmlFor = "hub-setting";
    var hub = el("input");
    hub.id = "hub-setting";
    hub.value = hubId();
    hub.addEventListener("change", function () {
      try { localStorage.setItem("resileos_hub_id", hub.value.trim() || "anon"); } catch (err) { /* ignore */ }
      note.textContent = "Saved. Chat in this browser now uses \u201c" + (hub.value.trim() || "anon") + "\u201d.";
    });
    var note = el("p", "msg", "");
    note.setAttribute("role", "status");
    form.append(debugWrap, hubLabel, hub, el("p", "micro", "Regular users never see these settings."), note);
    card.appendChild(form);
    return card;
  }

  async function statusCard() {
    var card = el("div", "card admin-card");
    card.appendChild(el("h3", "", "Service status"));
    var out = el("div", "admin-out");
    card.appendChild(out);
    var ready = await call("GET", "/ready").catch(function () { return { ok: false, status: "network", data: {} }; });
    var usage = await call("GET", "/usage").catch(function () { return { ok: false, status: "network", data: {} }; });
    out.appendChild(el("p", "admin-summary" + (ready.ok ? "" : " err"), ready.ok ? "The API is up." : "The API isn't answering (" + ready.status + ")."));
    var fold = el("details", "admin-raw");
    fold.appendChild(el("summary", "", "Raw status and usage"));
    fold.appendChild(el("pre", "", JSON.stringify({ ready: ready.data, usage: usage.data }, null, 2)));
    out.appendChild(fold);
    return card;
  }

  async function toolsList(grid) {
    var result = await call("GET", "/tools").catch(function () { return { ok: false, data: {} }; });
    var raw = [].concat((result.data && result.data.tools) || [], (result.data && result.data.harness) || []);
    var seen = {};
    raw.forEach(function (t) {
      var name = typeof t === "string" ? t : t && t.name;
      if (!name || seen[name]) return;
      seen[name] = true;
      var props = t && t.parameters && t.parameters.properties;
      var body = {};
      if (props) Object.keys(props).forEach(function (k) {
        var p = props[k] || {};
        body[k] = p.default !== undefined ? p.default : p.type === "boolean" ? false : p.type === "array" ? [] : (p.type === "number" || p.type === "integer") ? 0 : "";
      });
      var card = rawCard(name, "POST", "/tools/" + encodeURIComponent(name), body);
      if (t && t.description) card.querySelector(".admin-explain").textContent = t.description;
      grid.appendChild(card);
    });
    if (!Object.keys(seen).length) grid.appendChild(el("p", "admin-intro", result.ok ? "No tools listed." : "Couldn't list tools (" + result.status + ")."));
  }

  async function legionsList(grid) {
    var result = await call("GET", "/kin/legions").catch(function () { return { ok: false, data: {} }; });
    var catalog = (result.data && result.data.legions) || {};
    var kins = (result.data && result.data.kins) || Object.keys(catalog);
    var count = 0;
    kins.forEach(function (kin) {
      (catalog[kin] || []).forEach(function (item) {
        var name = item.name || item;
        count += 1;
        grid.appendChild(rawCard(kin + " / " + name, "POST", "/kin/legions/" + encodeURIComponent(kin) + "/" + encodeURIComponent(name), {}));
      });
    });
    if (!count) grid.appendChild(el("p", "admin-intro", result.ok ? "No helpers registered." : "Couldn't list helpers (" + result.status + ")."));
  }

  var STAGE = { packet: "iris", consistency: "iris", route: "metis", risk: "metis", budget: "metis", eat: "eat", review: "zeus", checkpoint: "hades", lesson: "hades" };

  /* Runs and replay: one run step by step in plain words (read-only). */
  function replayCard() {
    var card = el("div", "card admin-card replay-card");
    card.appendChild(el("h3", "", "Replay a run"));
    card.appendChild(el("p", "admin-explain", "Every chat turn and fact save is one run. Pick one to see each check it went through, in order. Only counts and results are kept, never what was typed."));
    var row = el("div", "cta-row");
    var load = el("button", "btn btn-ghost", "Show recent runs");
    load.type = "button";
    row.appendChild(load);
    var list = el("ul", "run-list");
    var steps = el("ol", "run-steps");
    card.append(row, list, steps);
    async function open(id) {
      steps.replaceChildren(el("li", "micro", "Loading\u2026"));
      var res = await call("GET", "/runs/" + encodeURIComponent(id));
      steps.replaceChildren();
      if (!res.ok) { steps.appendChild(el("li", "admin-summary err", summarize(res))); return; }
      var side = el("div", "separated-view");
      (res.data.steps || []).forEach(function (st) {
        var li = el("li", "run-step " + st.kind);
        var stage = STAGE[st.kind];
        if (stage) li.appendChild(el("span", "stage-tag " + stage, stage));
        li.appendChild(document.createTextNode(st.text));
        if (st.kind === "review") {
          var w = el("div", "sep-col");
          w.append(el("strong", "", "Writer proposed"), el("p", "", "A change, held until review"));
          var r = el("div", "sep-col");
          r.append(el("strong", "", "Reviewers (blind to the writer)"), el("p", "", ((st.data.reviewers || []).join(", ") || "none") + ": " + (st.data.applied ? "approved" : "not approved")));
          side.replaceChildren(w, r);
        }
        var fold = el("details", "admin-raw");
        fold.appendChild(el("summary", "", "Details"));
        fold.appendChild(el("pre", "", JSON.stringify(st.data, null, 2)));
        li.appendChild(fold);
        steps.appendChild(li);
      });
      if (side.childNodes.length) steps.after(side); else side.remove();
    }
    load.addEventListener("click", async function () {
      var res = await call("GET", "/runs?limit=20");
      list.replaceChildren();
      var runs = (res.data || {}).runs || [];
      if (!res.ok || !runs.length) { list.appendChild(el("li", "micro", res.ok ? "No runs yet." : summarize(res))); return; }
      runs.forEach(function (r) {
        var li = el("li", "");
        var b = el("button", "btn-link", (r.task || "run") + " \u00b7 " + new Date((r.started || 0) * 1000).toLocaleString() + " \u00b7 " + r.events + " steps");
        b.type = "button";
        b.addEventListener("click", function () { open(r.run); });
        li.appendChild(b);
        list.appendChild(li);
      });
    });
    return card;
  }

  // ---------- Operator ----------
  function kv(list, label, value) {
    var row = el("div", "kv");
    row.append(el("span", "k", label), el("span", "v", value === undefined || value === null || value === "" ? "\u2014" : String(value)));
    list.appendChild(row);
  }

  function packetCard() {
    var card = el("div", "card admin-card packet-card");
    card.appendChild(el("h3", "", "Control packet"));
    var body = el("div", "kv-list");
    var drawer = el("details", "evidence-drawer");
    drawer.appendChild(el("summary", "", "Evidence"));
    var ev = el("ul", "");
    drawer.appendChild(ev);
    card.append(body, drawer);
    card.refresh = async function () {
      var res = await call("GET", "/operator/state");
      body.replaceChildren();
      ev.replaceChildren();
      if (!res.ok) { body.appendChild(el("p", "admin-summary err", summarize(res))); return; }
      var c = res.data.control || {};
      if (!c.present) { body.appendChild(el("p", "micro", "No control packet yet. One starts with the first learning cycle.")); }
      else {
        kv(body, "Packet", c.id);
        kv(body, "Step", c.turn);
        kv(body, "Confidence", c.confidence);
        kv(body, "Safety", c.risk_class);
        kv(body, "Verified", c.verified ? "yes" : "no");
        kv(body, "Guides", (c.guides_loaded || []).join(", "));
        kv(body, "Scars", c.scars);
        kv(body, "Budget left", Object.keys(c.budget_remaining || {}).map(function (k) { return k + " " + c.budget_remaining[k]; }).join(", "));
        kv(body, "Recent events", (c.events || []).filter(Boolean).join(" \u2192 "));
        (c.evidence || []).forEach(function (e) { ev.appendChild(el("li", "", JSON.stringify(e))); });
        if (!(c.evidence || []).length) ev.appendChild(el("li", "micro", "No evidence attached yet."));
      }
      var cp = res.data.latest_checkpoint;
      kv(body, "Latest checkpoint", cp ? cp.id + (cp.verified ? " (verified)" : "") + (cp.lesson ? " \u2014 " + cp.lesson : "") : "none");
    };
    return card;
  }

  function hadesCard(after) {
    var card = el("div", "card admin-card");
    card.appendChild(el("h3", "", "Checkpoints"));
    card.appendChild(el("p", "admin-explain", "Save the current state, go back to the last verified one, or start fresh carrying only its lesson (no history, scars, or evidence)."));
    var row = el("div", "cta-row");
    var out = el("p", "admin-summary");
    [["Save checkpoint", "POST", "/kin/hades/save", {}, null],
     ["Restore latest verified", "POST", "/kin/hades/restore_latest_verified", {}, "Go back to the latest verified checkpoint?"],
     ["Restart from lesson only", "POST", "/kin/hades/restart_lesson", {}, "Start a fresh packet with only the latest lesson?"]].forEach(function (b) {
      var btn = el("button", "btn btn-ghost", b[0]);
      btn.type = "button";
      btn.addEventListener("click", async function () {
        if (b[4] && !window.confirm(b[4])) return;
        btn.disabled = true;
        var res = await call(b[1], b[2], b[3]);
        btn.disabled = false;
        out.textContent = res.ok ? ({ SAVED: "Saved checkpoint ", RESTORED: "Restored ", RESTARTED: "Restarted from the lesson of " }[res.data.status] || "") + (res.data.checkpoint_id || "") : summarize(res);
        out.className = "admin-summary" + (res.ok ? "" : " err");
        if (after) after();
      });
      row.appendChild(btn);
    });
    card.append(row, out);
    return card;
  }

  async function operatorPage(mount) {
    var top = group(mount, "Right now", "The live control packet and checkpoint controls.");
    var packet = packetCard();
    top.appendChild(packet);
    top.appendChild(hadesCard(function () { packet.refresh(); }));
    await packet.refresh();
    var runs = group(mount, "Runs and replay", "Every chat turn and fact save, step by step, tagged by the Kin that handled it.");
    runs.appendChild(replayCard());
  }

  async function diagnosticsPage(mount) {
    var top = group(mount, "Overview", "Health checks and settings for this browser.");
    top.appendChild(settingsCard());
    top.appendChild(await statusCard());
    var runs = group(mount, "Runs and replay", "");
    var moved = el("p", "admin-explain", "");
    var link = el("a", "", "Open Operator");
    link.href = "/admin/operator";
    moved.append(document.createTextNode("Run replay, checkpoints, and the control packet are on "), link, document.createTextNode("."));
    runs.appendChild(moved);
    RAW_TOOLS.forEach(function (section) {
      var grid = group(mount, section[0], "");
      section[1].forEach(function (t) { grid.appendChild(rawCard(t[0], t[1], t[2], t[3])); });
    });
    var tools = group(mount, "All tools", "Every tool the server lists, with a raw request you can edit.");
    var helpers = group(mount, "Kin helpers", "Specialist helpers registered on each Kin.");
    await Promise.all([toolsList(tools), legionsList(helpers)]);
  }

  async function init(active) {
    renderTabs(active);
    var gate = $("admin-gate");
    var content = $("admin-content");
    var account;
    try {
      account = await (window.ResileosAuth ? window.ResileosAuth.me() : fetch("/api/session/me", { credentials: "same-origin" }).then(function (r) { return r.json(); }));
    } catch (err) {
      account = { signed_in: false };
    }
    if (!account || !account.signed_in) {
      location.assign("/login?next=" + encodeURIComponent(location.pathname));
      return null;
    }
    csrf = account.csrf || "";
    if (!account.admin) {
      if (gate) { gate.hidden = false; gate.textContent = "This page is for site admins only."; }
      if (content) content.hidden = true;
      return null;
    }
    if (gate) gate.hidden = true;
    if (content) {
      content.hidden = false;
      if (active === "knowledge") knowledgePage(content);
      if (active === "operator") await operatorPage(content);
      if (active === "diagnostics") await diagnosticsPage(content);
    }
    return account;
  }

  window.ResileosAdmin = { init: init, renderTabs: renderTabs, call: call, summarize: summarize };
  var page = document.body && document.body.dataset.adminPage;
  if (page && page !== "reports") init(page);
  else if (page === "reports") renderTabs("reports");
})();
