/* Admin console: Reports, Knowledge, Diagnostics.
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

  // ---------- Knowledge ----------
  function knowledgePage(mount) {
    var add = group(mount, "Add and check facts",
      "Facts are short statements like \u201cAlice works at Acme\u201d. Every fact goes through the same accuracy checks before it is saved. Anything that fails a check is skipped, never forced in.");
    add.appendChild(toolCard({
      title: "Add facts from text",
      explain: "Paste notes or an article. Studio pulls out simple facts. By default this is a preview and nothing is saved.",
      fields: [
        { name: "text", label: "Text", type: "textarea", placeholder: "Alice works at Acme. Acme is based in Lisbon." },
        { name: "commit", label: "Save the facts that pass the checks", type: "checkbox", value: false,
          help: "Leave this off to see what would be saved first." },
      ],
      button: "Find facts",
      run: function (v) {
        if (!v.text) return { error: "Paste some text first." };
        return { method: "POST", path: "/studio/graphify", body: { source: v.text, commit: Boolean(v.commit) } };
      },
    }));
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

  async function diagnosticsPage(mount) {
    var top = group(mount, "Overview", "Health checks and settings for this browser.");
    top.appendChild(settingsCard());
    top.appendChild(await statusCard());
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
      if (active === "diagnostics") await diagnosticsPage(content);
    }
    return account;
  }

  window.ResileosAdmin = { init: init, renderTabs: renderTabs, call: call, summarize: summarize };
  var page = document.body && document.body.dataset.adminPage;
  if (page && page !== "reports") init(page);
  else if (page === "reports") renderTabs("reports");
})();
