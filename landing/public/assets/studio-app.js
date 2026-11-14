/* Studio app shell: projects with three pillars (worlds, clips, pictures)
 * on one asset board. Talks to /api/session/v1/studio-projects through the
 * signed-in session. Made things are labelled "not checked"; nothing here
 * is ever presented as a fact. */
(function () {
  "use strict";
  var API = "/api/session/v1/studio-projects";
  var csrf = "";
  var signedIn = false;
  var project = null;
  var picked = {};           // asset id -> true (batch selection)
  var layers = [];           // pending edit layers
  var playing = null;
  var saveTimer = null;
  var providerReady = false;

  function $(id) { return document.getElementById(id); }
  function el(tag, attrs, kids) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "text") n.textContent = attrs[k];
      else if (k === "class") n.className = attrs[k];
      else if (k.indexOf("on") === 0) n.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] !== undefined && attrs[k] !== null && attrs[k] !== false) n.setAttribute(k, attrs[k] === true ? "" : attrs[k]);
    });
    (kids || []).forEach(function (c) { if (c) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return n;
  }
  function status(text, kind) { var s = $("sa-status"); s.textContent = text || ""; s.dataset.kind = kind || ""; }
  function headers(json) {
    var h = {};
    if (json) h["Content-Type"] = "application/json";
    if (csrf) h["X-CSRF-Token"] = csrf;
    return h;
  }
  async function call(method, path, body) {
    var res = await fetch(API + path, { method: method, credentials: "same-origin", headers: headers(body !== undefined), body: body === undefined ? undefined : JSON.stringify(body) });
    var data = await res.json().catch(function () { return {}; });
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : res.status === 401 ? "Sign in to use Studio projects." : "Something went wrong. Try again.");
    return data;
  }

  /* ── views ─────────────────────────────────────────────────────── */
  function show(view) {
    if (!project && document.querySelector('.sa-nav a[data-view="' + view + '"][data-needs-project]')) view = "projects";
    document.querySelectorAll(".sa-view").forEach(function (s) { s.hidden = s.dataset.view !== view; });
    document.querySelectorAll(".sa-nav a").forEach(function (a) {
      if (a.dataset.view === view) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
      if (a.hasAttribute("data-needs-project")) a.classList.toggle("is-off", !project);
    });
    if (view !== "make" && location.hash !== "#" + view) history.replaceState(null, "", "#" + view + (project ? "/" + project.id : ""));
    render(view);
  }
  function currentView() {
    var v = (location.hash || "#projects").slice(1).split("/")[0];
    return document.querySelector('.sa-view[data-view="' + v + '"]') ? v : "projects";
  }

  /* ── drawing ───────────────────────────────────────────────────── */
  function frameOf(asset) { return asset.matrix || (asset.frames && asset.frames[0]) || null; }
  function canvasFor(frame, w, h) {
    var c = el("canvas", { width: w || 120, height: h || 90, class: "sa-thumb" });
    if (frame && window.ResileosMedia) window.ResileosMedia.drawFrame(c, frame);
    return c;
  }
  function label(asset) {
    if (asset.source === "made" || asset.source === "dream") return "Made · not checked";
    if (asset.source === "chat") return "From chat";
    return "Yours";
  }
  function assetCard(asset, opts) {
    opts = opts || {};
    var isPick = project.picks && project.picks[0] === asset.id;
    var box = el("div", { class: "sa-asset" + (picked[asset.id] ? " is-picked" : "") + (isPick ? " is-best" : ""), "data-id": asset.id });
    box.appendChild(canvasFor(frameOf(asset), opts.w || 120, opts.h || 90));
    box.appendChild(el("span", { class: "sa-asset-name", text: asset.name }));
    box.appendChild(el("span", { class: "sa-tag " + (asset.source === "made" ? "unverified" : ""), text: (asset.kind === "clip" ? "Clip · " : "") + label(asset) }));
    if (opts.select) {
      var cb = el("input", { type: "checkbox", "aria-label": "Pick " + asset.name });
      cb.checked = !!picked[asset.id];
      cb.addEventListener("change", function () { if (cb.checked) picked[asset.id] = true; else delete picked[asset.id]; box.classList.toggle("is-picked", cb.checked); });
      box.prepend(el("label", { class: "sa-check" }, [cb]));
    }
    if (opts.details) {
      var d = el("details", { class: "details" }, [el("summary", { text: "Details" })]);
      var dl = el("dl", { class: "details-list" });
      [["Color code", asset.code || "—"], ["Address", (asset.address && asset.address.path) || "—"], ["Made from", asset.parent || "—"],
       ["Edits", (asset.layers || []).map(function (l) { return l.kind; }).join(", ") || "—"]].forEach(function (row) {
        dl.appendChild(el("dt", { text: row[0] })); dl.appendChild(el("dd", { text: row[1] }));
      });
      d.appendChild(dl);
      box.appendChild(d);
    }
    if (opts.onclick) box.addEventListener("click", function (e) { if (e.target.tagName !== "INPUT" && e.target.tagName !== "SUMMARY") opts.onclick(asset); });
    return box;
  }

  /* ── editable lists ────────────────────────────────────────────── */
  function field(value, placeholder, onchange, attrs) {
    var input = el(attrs && attrs.multiline ? "textarea" : "input", Object.assign({ placeholder: placeholder, "aria-label": placeholder }, attrs && attrs.multiline ? { rows: 2 } : {}, attrs && attrs.type ? { type: attrs.type } : {}));
    input.value = value == null ? "" : value;
    input.addEventListener("change", function () { onchange(attrs && attrs.type === "number" ? Number(input.value) : input.value); save(); });
    return input;
  }
  function removeBtn(list, i, what) {
    return el("button", { class: "btn-link sa-remove", type: "button", "aria-label": "Remove " + what, text: "Remove", onclick: function () { list.splice(i, 1); save(); rerender(); } });
  }
  function rows(target, list, cols, what) {
    var host = $(target);
    host.innerHTML = "";
    if (!list.length) { host.appendChild(el("p", { class: "micro sa-empty", text: "Nothing yet." })); return; }
    list.forEach(function (item, i) {
      var row = el("div", { class: "sa-line" });
      cols.forEach(function (c) {
        if (c.select) {
          var s = el("select", { "aria-label": c.label });
          c.select().forEach(function (o) { var opt = el("option", { value: o[0], text: o[1] }); if (String(item[c.key]) === String(o[0])) opt.selected = true; s.appendChild(opt); });
          s.addEventListener("change", function () { item[c.key] = s.value; save(); });
          row.appendChild(s);
        } else {
          row.appendChild(field(item[c.key], c.label, function (v) { item[c.key] = v; }, c));
        }
      });
      row.appendChild(removeBtn(list, i, what));
      host.appendChild(row);
    });
  }
  function rid() {
    var a = new Uint8Array(8);
    (window.crypto || window.msCrypto).getRandomValues(a);
    return Array.prototype.map.call(a, function (b) { return ("0" + b.toString(16)).slice(-2); }).join("");
  }
  var NEW = {
    lore: function () { return { title: "", text: "" }; },
    places: function () { return { name: "", notes: "" }; },
    factions: function () { return { name: "", notes: "" }; },
    timeline: function () { return { subject: "", relation: "", object: "", valid_from: "", valid_to: "" }; },
    characters: function () { return { name: "New character", role: "", voice: "honest", notes: "" }; },
    scenes: function () { return { title: "New scene", summary: "", place: "", characters: [], shots: [] }; },
    stats: function () { return { name: "stat" + ((project.game.stats || []).length + 1), min: 0, max: 100, start: 50 }; },
    entities: function () { return { name: "", stats: {} }; },
    rules: function () { var s = project.game.stats[0]; return { name: "", stat: s ? s.name : "", change: -1 }; },
    invariants: function () { var s = project.game.stats[0]; return { stat: s ? s.name : "", op: ">=", value: 0 }; }
  };
  function listFor(kind) {
    if (["lore", "places", "factions", "timeline"].indexOf(kind) !== -1) return project.bible[kind];
    if (["stats", "entities", "rules", "invariants"].indexOf(kind) !== -1) return project.game[kind];
    return project[kind];
  }

  /* ── renderers ─────────────────────────────────────────────────── */
  function renderProjects(list) {
    var host = $("project-list");
    host.innerHTML = "";
    $("signin-note").hidden = signedIn;
    (list || []).forEach(function (p) {
      var card = el("article", { class: "sa-card sa-project-card" + (project && project.id === p.id ? " is-open" : "") }, [
        el("h2", { text: p.name }),
        el("p", { class: "micro", text: (p.counts.assets || 0) + " assets · " + (p.counts.characters || 0) + " characters · " + (p.counts.scenes || 0) + " scenes" }),
        el("div", { class: "sa-row" }, [
          el("button", { class: "btn btn-primary", type: "button", text: "Open", onclick: function () { open(p.id, "world"); } }),
          el("button", { class: "btn btn-ghost", type: "button", text: "Delete", onclick: async function () {
            if (!confirm("Delete “" + p.name + "”? This can't be undone.")) return;
            await call("DELETE", "/" + p.id);
            if (project && project.id === p.id) { project = null; $("sa-project-name").textContent = "No project open"; }
            loadList();
          } })
        ])
      ]);
      host.appendChild(card);
    });
    if (signedIn && !(list || []).length) host.appendChild(el("p", { class: "micro", text: "No projects yet. Name one above to start." }));
  }
  function renderWorld() {
    var b = project.bible;
    rows("lore-list", b.lore, [{ key: "title", label: "Title" }, { key: "text", label: "What happened", multiline: true }], "lore");
    rows("places-list", b.places, [{ key: "name", label: "Place" }, { key: "notes", label: "Notes" }], "place");
    rows("factions-list", b.factions, [{ key: "name", label: "Faction" }, { key: "notes", label: "Notes" }], "faction");
    rows("timeline-list", b.timeline, [{ key: "subject", label: "Who or what" }, { key: "relation", label: "How" }, { key: "object", label: "What" },
      { key: "valid_from", label: "From (year or date)" }, { key: "valid_to", label: "Until" }], "timeline line");
    worldDepth();
  }
  async function worldDepth() {
    await flush();
    var f = Number((document.querySelector('input[name="depth"]:checked') || {}).value || 3);
    var out = await call("POST", "/" + project.id + "/op/world_level", { frame: f });
    var tree = $("world-tree");
    tree.innerHTML = "";
    out.result.nodes.forEach(function (n) { tree.appendChild(el("li", { class: "depth-" + n.depth, text: (n.name || "(unnamed)") + " · " + n.kind })); });
  }
  function renderCharacters() {
    var host = $("character-list");
    host.innerHTML = "";
    project.characters.forEach(function (c, i) {
      host.appendChild(el("article", { class: "sa-card" }, [
        field(c.name, "Name", function (v) { c.name = v; }),
        field(c.role, "Role", function (v) { c.role = v; }),
        field(c.notes, "Notes", function (v) { c.notes = v; }, { multiline: true }),
        (function () {
          var s = el("select", { "aria-label": "Voice" });
          [["honest", "Plain"], ["warm", "Warm"], ["terse", "Short"]].forEach(function (o) { var opt = el("option", { value: o[0], text: o[1] }); if (c.voice === o[0]) opt.selected = true; s.appendChild(opt); });
          s.addEventListener("change", function () { c.voice = s.value; save(); });
          return s;
        })(),
        el("p", { class: "micro", text: "Kept in your personal tier." }),
        removeBtn(project.characters, i, "character")
      ]));
    });
  }
  function renderScenes() {
    var host = $("scene-list");
    host.innerHTML = "";
    var pics = project.assets.filter(function (a) { return a.kind === "image"; });
    project.scenes.forEach(function (s, i) {
      var shots = el("div", { class: "sa-shots" });
      s.shots.forEach(function (shot, j) {
        var a = project.assets.filter(function (x) { return x.id === shot.asset; })[0];
        shots.appendChild(el("div", { class: "sa-shot" }, [
          a ? canvasFor(frameOf(a), 96, 72) : el("span", { class: "micro", text: "Missing" }),
          field(shot.hold, "Hold", function (v) { shot.hold = Math.max(1, Math.min(12, v || 1)); }, { type: "number" }),
          removeBtn(s.shots, j, "shot")
        ]));
      });
      var add = el("select", { "aria-label": "Add a shot" }, [el("option", { value: "", text: pics.length ? "Add a shot…" : "Add pictures first" })]);
      pics.forEach(function (p) { add.appendChild(el("option", { value: p.id, text: p.name })); });
      add.addEventListener("change", function () { if (add.value) { s.shots.push({ asset: add.value, hold: 1, note: "" }); save(); renderScenes(); } });
      var place = el("select", { "aria-label": "Place" }, [el("option", { value: "", text: "No place" })]);
      project.bible.places.forEach(function (p) { var o = el("option", { value: p.id, text: p.name || "(unnamed)" }); if (s.place === p.id) o.selected = true; place.appendChild(o); });
      place.addEventListener("change", function () { s.place = place.value; save(); });
      host.appendChild(el("article", { class: "sa-card" }, [
        field(s.title, "Scene title", function (v) { s.title = v; }),
        field(s.summary, "What happens", function (v) { s.summary = v; }, { multiline: true }),
        place, el("h3", { text: "Storyboard" }), shots, add,
        el("div", { class: "sa-row" }, [
          el("button", { class: "btn btn-primary", type: "button", text: "Make clip from storyboard", onclick: function () { make("storyboard_clip", { scene: s.id }, "video-result"); } }),
          removeBtn(project.scenes, i, "scene")
        ])
      ]));
    });
  }
  function renderGame() {
    var g = project.game;
    var statOpts = function () { return g.stats.map(function (s) { return [s.name, s.name]; }); };
    rows("stats-list", g.stats, [{ key: "name", label: "Name" }, { key: "min", label: "Lowest", type: "number" }, { key: "max", label: "Highest", type: "number" }, { key: "start", label: "Starts at", type: "number" }], "stat");
    var ent = $("entities-list");
    ent.innerHTML = "";
    g.entities.forEach(function (e, i) {
      var row = el("div", { class: "sa-line" }, [field(e.name, "Name", function (v) { e.name = v; })]);
      g.stats.forEach(function (s) { row.appendChild(field(e.stats[s.name] != null ? e.stats[s.name] : s.start, s.name, function (v) { e.stats[s.name] = v; }, { type: "number" })); });
      row.appendChild(removeBtn(g.entities, i, "thing"));
      ent.appendChild(row);
    });
    if (!g.entities.length) ent.appendChild(el("p", { class: "micro sa-empty", text: "Nothing yet. Rules run on a default thing." }));
    rows("rules-list", g.rules, [{ key: "name", label: "Rule" }, { key: "stat", label: "Stat", select: statOpts }, { key: "change", label: "Change per round", type: "number" }], "rule");
    rows("invariants-list", g.invariants, [{ key: "stat", label: "Stat", select: statOpts }, { key: "op", label: "Is", select: function () { return [[">=", "at least"], ["<=", "at most"], ["==", "exactly"]]; } }, { key: "value", label: "Value", type: "number" }], "check");
  }
  function pickList(target, filter) {
    var host = $(target);
    host.innerHTML = "";
    var list = project.assets.filter(filter);
    if (!list.length) host.appendChild(el("p", { class: "micro", text: "Nothing to pick yet." }));
    list.forEach(function (a) { host.appendChild(assetCard(a, { select: true, w: 96, h: 72 })); });
  }
  function renderVideo() {
    var tl = $("video-timeline");
    tl.innerHTML = "";
    var clips = project.assets.filter(function (a) { return a.kind === "clip"; });
    if (!clips.length) tl.appendChild(el("p", { class: "micro", text: "No clips yet. Make one below." }));
    clips.forEach(function (c) { tl.appendChild(assetCard(c, { w: 112, h: 72, onclick: play })); });
    pickList("video-pictures", function (a) { return a.kind === "image"; });
    pickList("video-clips", function (a) { return a.kind === "clip"; });
    var sel = $("t2v-scene"), keep = sel.value;
    sel.innerHTML = "";
    sel.appendChild(el("option", { value: "", text: "No scene" }));
    (project.scenes || []).forEach(function (s) { sel.appendChild(el("option", { value: s.id, text: s.title || "Untitled scene" })); });
    sel.value = keep;
    $("provider-note").textContent = "Pick a scene set in one of your places and we'll pan across that world's map. Your words alone aren't turned into pictures. " +
      (providerReady ? "Without a scene, the configured video provider is used." : "Without a scene, it's unavailable: no video provider is set up, and nothing will be faked.");
    $("make-t2v").disabled = false;
  }
  function renderImage() {
    pickList("image-pictures", function (a) { return a.kind === "image"; });
    renderLayers();
    var cmp = $("compare");
    cmp.innerHTML = "";
    var made = project.assets.filter(function (a) { return a.kind === "image"; }).slice(-8);
    made.sort(function (a, b) { return (project.picks.indexOf(b.id) === 0) - (project.picks.indexOf(a.id) === 0); });
    made.forEach(function (a) {
      var card = assetCard(a, { w: 160, h: 120, details: true });
      card.appendChild(el("button", { class: "btn btn-ghost", type: "button", text: project.picks[0] === a.id ? "Picked" : "Pick this", onclick: async function () {
        var out = await call("POST", "/" + project.id + "/op/pick", { asset: a.id });
        project = out.project; renderImage();
      } }));
      card.appendChild(el("button", { class: "btn-link", type: "button", text: "Show levels", onclick: function () { levels(a.id); } }));
      cmp.appendChild(card);
    });
  }
  async function levels(id) {
    var out = await call("POST", "/" + project.id + "/op/levels", { asset: id });
    var host = $("levels");
    host.innerHTML = "";
    out.result.levels.forEach(function (l) {
      host.appendChild(el("figure", {}, [canvasFor(l.matrix, 120, 90), el("figcaption", { text: l.frame.frame + " blocks" + (l.frame.orientation ? " · orientation" : "") })]));
    });
  }
  var LAYER_LABEL = { tone: "Brightness and contrast", recolor: "Recolor", orientation: "Scale color", level: "Simplify", flip: "Mirror", crop: "Crop", overlay: "Lay another picture over" };
  function renderLayers() {
    var host = $("layer-list");
    host.innerHTML = "";
    if (!layers.length) host.appendChild(el("p", { class: "micro", text: "No edits yet." }));
    layers.forEach(function (l, i) {
      var row = el("div", { class: "sa-line" }, [el("strong", { text: LAYER_LABEL[l.kind] })]);
      function num(key, lbl, min, max, step) {
        var input = el("input", { type: "range", min: min, max: max, step: step, "aria-label": lbl });
        input.value = l[key];
        input.addEventListener("input", function () { l[key] = Number(input.value); });
        row.appendChild(el("label", { class: "sa-range" }, [lbl, input]));
      }
      if (l.kind === "tone") { num("brightness", "Brightness", -0.5, 0.5, 0.05); num("contrast", "Contrast", 0.2, 2, 0.1); }
      if (l.kind === "recolor") num("variant", "Variant", 1, 12, 1);
      if (l.kind === "crop") { num("x", "Left", 0, 0.9, 0.05); num("y", "Top", 0, 0.9, 0.05); num("w", "Width", 0.1, 1, 0.05); num("h", "Height", 0.1, 1, 0.05); }
      if (l.kind === "level" || l.kind === "orientation" || l.kind === "overlay" || l.kind === "flip") {
        var s = el("select", { "aria-label": LAYER_LABEL[l.kind] });
        var opts = l.kind === "level" ? [["3", "Very simple"], ["5", "Simple"], ["9", "Light"], ["12", "Lightest"]]
          : l.kind === "orientation" ? [["edge", "Close up"], ["sun_earth_moon", "Near"], ["orion", "Far"], ["north_star", "Farthest"]]
          : l.kind === "flip" ? [["h", "Left to right"], ["v", "Top to bottom"]]
          : project.assets.filter(function (a) { return a.kind === "image"; }).map(function (a) { return [a.id, a.name]; });
        var key = l.kind === "level" ? "frame" : l.kind === "orientation" ? "scale" : l.kind === "flip" ? "axis" : "asset";
        opts.forEach(function (o) { var opt = el("option", { value: o[0], text: o[1] }); if (String(l[key]) === o[0]) opt.selected = true; s.appendChild(opt); });
        s.addEventListener("change", function () { l[key] = key === "frame" ? Number(s.value) : s.value; });
        if (l[key] === undefined && opts[0]) l[key] = key === "frame" ? Number(opts[0][0]) : opts[0][0];
        row.appendChild(s);
        if (l.kind === "overlay") num("alpha", "Amount", 0.1, 1, 0.05);
      }
      row.appendChild(el("button", { class: "btn-link sa-remove", type: "button", text: "Remove", onclick: function () { layers.splice(i, 1); renderLayers(); } }));
      host.appendChild(row);
    });
  }
  function renderAssets() {
    var host = $("asset-board");
    host.innerHTML = "";
    if (!project.assets.length) host.appendChild(el("p", { class: "micro", text: "No assets yet. Add pictures in Pictures." }));
    project.assets.forEach(function (a, i) {
      var card = assetCard(a, { w: 160, h: 120, details: true, onclick: a.kind === "clip" ? play : null });
      card.appendChild(field(a.name, "Name", function (v) { a.name = v; }));
      card.appendChild(removeBtn(project.assets, i, "asset"));
      host.appendChild(card);
    });
  }
  function render(view) {
    if (view === "projects") return loadList();
    if (!project) return;
    ({ world: renderWorld, characters: renderCharacters, scenes: renderScenes, game: renderGame, video: renderVideo, image: renderImage, assets: renderAssets }[view] || function () {})();
  }
  function rerender() { render(currentView()); }

  /* ── actions ───────────────────────────────────────────────────── */
  var pending = null;
  async function push() {
    saveTimer = null;
    var body = JSON.parse(JSON.stringify(project));
    body.assets = body.assets.map(function (a) { return { id: a.id, name: a.name, note: a.note }; });
    try {
      var saved = await call("PUT", "/" + project.id, body);
      // Rows carry their own ids, so the open editors keep pointing at
      // the same objects; only the save time comes back.
      project.updated_at = saved.updated_at;
      status("Saved");
    } catch (err) { status(err.message, "error"); }
  }
  function save() {
    if (!project) return;
    clearTimeout(saveTimer);
    status("Saving…");
    saveTimer = setTimeout(function () { pending = push(); }, 400);
  }
  /* Before a check or a make, write any edit still waiting. */
  async function flush() {
    if (saveTimer) { clearTimeout(saveTimer); pending = push(); }
    if (pending) await pending;
  }
  async function open(id, view) {
    try {
      project = await call("GET", "/" + id);
      picked = {}; layers = [];
      $("sa-project-name").textContent = project.name;
      show(view || "world");
    } catch (err) { status(err.message, "error"); }
  }
  async function loadList() {
    if (!signedIn) { renderProjects([]); return; }
    try {
      var out = await call("GET", "");
      providerReady = !!(out.video_provider && out.video_provider.configured);
      renderProjects(out.projects);
    } catch (err) { status(err.message, "error"); }
  }
  function selected(kind) { return project.assets.filter(function (a) { return picked[a.id] && (!kind || a.kind === kind); }).map(function (a) { return a.id; }); }

  /* Long operations run on the shared stream layer; plain call as fallback. */
  async function make(op, body, resultId) {
    await flush();
    var out = $(resultId);
    out.innerHTML = "";
    var trail = el("ul", { class: "trail live" });
    out.appendChild(trail);
    status("Working…");
    var final = null, error = null;
    var res = window.ResileosParts ? await window.ResileosParts.run({
      url: API + "/" + project.id + "/stream/" + op, body: body, headers: headers(true),
      resumeUrl: function (id) { return "/api/session/v1/chat/stream/" + id; },
      fallback: function () { return call("POST", "/" + project.id + "/op/" + op, body); },
      onPart: function (p) {
        if (p.type === "step") trail.appendChild(el("li", { class: "trail-step " + p.status, text: p.label }));
        if (p.type === "final") final = p;
        if (p.type === "error") error = p.label;
      }
    }) : { fallback: true, result: await call("POST", "/" + project.id + "/op/" + op, body) };
    if (res && res.error && res.response) { var d = await res.response.json().catch(function () { return {}; }); error = d.detail || "Couldn't make that."; }
    if (error) { status(error, "error"); out.appendChild(el("p", { class: "sa-msg error", text: error })); return; }
    project = await call("GET", "/" + project.id);
    var result = res && res.fallback ? res.result.result : (final && final.assist && final.assist.result) || {};
    if ((final && final.status === "UNAVAILABLE") || result.status === "UNAVAILABLE") {
      status("Unavailable");
      out.appendChild(el("p", { class: "sa-msg unavailable", text: "Nothing was made: " + (result.detail || "no provider is set up.") + " We won't pretend." }));
    } else {
      status("Done");
      out.appendChild(el("p", { class: "sa-msg", text: "Made. These haven't been checked." }));
      if (result.summary && result.summary.length) {
        var ul = el("ul", { class: "sa-summary" });
        result.summary.forEach(function (t) { ul.appendChild(el("li", { text: t })); });
        out.appendChild(ul);
      }
      if (result.details && (result.details.confidence != null || result.details.cost)) {
        var d = result.details, bits = [];
        if (d.confidence != null) bits.push("Confidence " + Math.round(d.confidence * 100) + "%");
        if (d.cost) bits.push(d.cost.seconds + " s, " + d.cost.memory_mb + " MB");
        if (d.source) bits.push(d.source);
        var det = el("details", {}, [el("summary", { text: "Details" }), el("p", { class: "micro", text: bits.join(" · ") })]);
        out.appendChild(det);
      }
    }
    rerender();
    return result;
  }

  async function upload(files) {
    var list = Array.prototype.slice.call(files || []);
    for (var i = 0; i < list.length; i++) {
      var f = list[i];
      try {
        status("Reading " + f.name + "…");
        var isClip = /^video\//.test(f.type);
        var data = isClip ? await window.ResileosMedia.readVideo(f, 48) : await window.ResileosMedia.readImage(f, 64);
        var body = { name: f.name, thumb: data.thumb, kind: isClip ? "clip" : "image" };
        if (isClip) body.frames = data.rgb; else body.matrix = data.rgb;
        var out = await call("POST", "/" + project.id + "/op/add_asset", body);
        project = out.project;
      } catch (err) { status(err.message, "error"); }
    }
    status("Added");
    rerender();
  }

  function play(asset) {
    if (playing) clearInterval(playing);
    var frames = asset.frames || [asset.matrix];
    var c = $("player"), i = 0;
    $("player-label").textContent = asset.name + " · " + label(asset);
    if (currentView() !== "video") show("video");
    playing = setInterval(function () {
      window.ResileosMedia.drawFrame(c, frames[i % frames.length]);
      i++;
      if (i > frames.length * 3) { clearInterval(playing); playing = null; }
    }, 125);
  }

  function drawMap(m) {
    var c = $("world-map"), ctx = c.getContext("2d"), n = m.length, px = c.width / n;
    c.hidden = false;
    for (var i = 0; i < n; i++) for (var j = 0; j < m[i].length; j++) {
      var v = m[i][j];
      ctx.fillStyle = "rgb(" + Math.round(v[0] * 255) + "," + Math.round(v[1] * 255) + "," + Math.round(v[2] * 255) + ")";
      ctx.fillRect(j * px, i * px, Math.ceil(px), Math.ceil(px));
    }
  }

  function result(target, items, ok) {
    var host = $(target);
    host.innerHTML = "";
    host.appendChild(el("p", { class: "sa-msg " + (ok ? "ok" : "warn"), text: ok ? "All checks pass." : "Some things don't fit:" }));
    var ul = el("ul");
    items.forEach(function (t) { ul.appendChild(el("li", { text: t })); });
    host.appendChild(ul);
  }

  function wire() {
    document.querySelectorAll(".sa-nav a").forEach(function (a) {
      a.addEventListener("click", function (e) { e.preventDefault(); show(a.dataset.view); });
    });
    $("sa-project-name").addEventListener("click", function () { show("projects"); });
    $("new-project").addEventListener("submit", async function (e) {
      e.preventDefault();
      try {
        var p = await call("POST", "", { name: $("np-name").value });
        $("np-name").value = "";
        open(p.id, "world");
      } catch (err) { status(err.message, "error"); }
    });
    document.querySelectorAll("[data-add]").forEach(function (b) {
      b.addEventListener("click", function () {
        var row = NEW[b.dataset.add]();
        if (b.dataset.add !== "stats") row.id = rid();  // ids are made here, so edits never race a save
        listFor(b.dataset.add).push(row); save(); rerender();
      });
    });
    document.querySelectorAll('input[name="depth"]').forEach(function (r) { r.addEventListener("change", worldDepth); });
    var mapSeed = 0;
    async function buildWorld() {
      var res = await make("build_world", mapSeed ? { seed: project.id + "/" + mapSeed } : {}, "world-map-result");
      if (!res || res.status !== "MADE") return;
      var maps = project.assets.filter(function (a) { return a.name === "World map" && a.matrix; });
      if (maps.length) drawMap(maps[maps.length - 1].matrix);
    }
    $("build-world").addEventListener("click", function () { mapSeed = 0; buildWorld(); });
    $("rebuild-world").addEventListener("click", function () { mapSeed += 1; buildWorld(); });
    $("check-world").addEventListener("click", async function () {
      await flush();
      var out = (await call("POST", "/" + project.id + "/op/check", {})).result;
      result("world-check", out.timeline.problems.map(function (p) { return p.text; }), out.timeline.ok);
    });
    $("dream").addEventListener("click", async function () {
      await flush();
      var out = (await call("POST", "/" + project.id + "/op/dream", { n: 4, seed: Math.floor(Math.random() * 1000) })).result;
      var ul = $("dream-list");
      ul.innerHTML = "";
      if (!out.ideas.length) ul.appendChild(el("li", { class: "micro", text: "Add places, factions, or characters first." }));
      out.ideas.forEach(function (i) { ul.appendChild(el("li", {}, [el("span", { class: "sa-tag unverified", text: "Dream · not checked" }), " " + i.idea])); });
    });
    $("opt-in").addEventListener("change", function () { $("promote").disabled = !$("opt-in").checked; });
    $("promote").addEventListener("click", async function () {
      await flush();
      try {
        var out = (await call("POST", "/" + project.id + "/op/promote", { opt_in: $("opt-in").checked })).result;
        var host = $("promote-result");
        host.innerHTML = "";
        out.preview.items.forEach(function (it) { host.appendChild(el("p", { class: "sa-msg", text: it.status })); });
        host.appendChild(el("p", { class: "micro", text: out.note }));
      } catch (err) { status(err.message, "error"); }
    });
    $("run-rules").addEventListener("click", async function () {
      await flush();
      var out = (await call("POST", "/" + project.id + "/op/check", {})).result;
      result("game-check", out.game.problems.map(function (p) { return p.text; }), out.game.ok);
    });
    $("lean-rules").addEventListener("click", async function () {
      await flush();
      status("Checking…");
      var out = (await call("POST", "/" + project.id + "/op/lean", {})).result;
      var text = out.status === "CHECKED" ? "Proved: the starting values fit their ranges and checks." : out.status === "NOTHING" ? out.summary : "Not proved: " + (out.summary || out.status);
      $("game-check").innerHTML = "";
      $("game-check").appendChild(el("p", { class: "sa-msg " + (out.status === "CHECKED" ? "ok" : "warn"), text: text }));
      status("");
    });
    $("make-clip").addEventListener("click", function () {
      var ids = selected("image");
      if (!ids.length) { status("Pick one or more pictures.", "error"); return; }
      make("clip", { assets: ids }, "video-result");
    });
    $("recolor-clip").addEventListener("click", function () {
      var ids = selected("clip");
      if (!ids.length) { status("Pick a clip.", "error"); return; }
      make("recolor_clip", { asset: ids[0], variant: 1 + Math.floor(Math.random() * 6) }, "video-result");
    });
    $("make-t2v").addEventListener("click", function () {
      if (!$("t2v").value.trim()) { status("Describe the video.", "error"); return; }
      make("text_to_video", { prompt: $("t2v").value, scene: $("t2v-scene").value || null }, "video-result");
    });
    $("play").addEventListener("click", function () {
      var clips = project && project.assets.filter(function (a) { return a.kind === "clip"; });
      if (clips && clips.length) play(clips[clips.length - 1]);
    });
    $("sa-upload").addEventListener("change", function (e) { upload(e.target.files); e.target.value = ""; });
    $("make-variations").addEventListener("click", function () {
      var ids = selected("image");
      if (!ids.length) { status("Pick a picture.", "error"); return; }
      make("variations", { asset: ids[0], n: Number($("var-n").value), orientation: $("var-scale").value || null }, "image-result");
    });
    $("add-layer").addEventListener("click", function () {
      var kind = $("layer-kind").value;
      layers.push({ kind: kind, brightness: 0, contrast: 1, variant: 1, x: 0, y: 0, w: 1, h: 1, alpha: 0.5 });
      renderLayers();
    });
    $("apply-layers").addEventListener("click", function () {
      var ids = selected("image");
      if (!ids.length || !layers.length) { status("Pick pictures and add at least one edit.", "error"); return; }
      make("edit", { assets: ids, layers: layers }, "image-result");
    });
    window.addEventListener("hashchange", function () {
      var parts = location.hash.slice(1).split("/");
      if (parts[1] && (!project || project.id !== parts[1])) open(parts[1], parts[0]); else show(currentView());
    });
  }

  /* Chat's "make from this": the attachment starts a new project. */
  async function fromChat(handed) {
    var first = handed.rgb && handed.rgb[0];
    var body = { name: (handed.name ? "From chat: " + handed.name : "From chat").slice(0, 120), from_chat: {
      name: handed.name || "From chat", thumb: handed.thumb || "", kind: handed.type === "clip" ? "clip" : "image" } };
    if (handed.type === "clip" && handed.rgb && handed.rgb.length > 1) body.from_chat.frames = handed.rgb;
    else if (first) body.from_chat.matrix = first;
    else if (handed.frames && handed.frames.length) body.from_chat.matrix = handed.frames[0];
    var p = await call("POST", "", body);
    open(p.id, handed.type === "clip" ? "video" : "image");
  }

  async function start() {
    wire();
    var me = window.ResileosNav ? window.ResileosNav.session() : fetch("/api/session/me", { credentials: "same-origin" }).then(function (r) { return r.json(); });
    var account = await Promise.resolve(me).catch(function () { return null; });
    csrf = (account && account.csrf) || "";
    signedIn = !!(account && account.signed_in);
    var parts = (location.hash || "").slice(1).split("/");
    var handed = window.__studioHandoff;
    if (handed && signedIn) { try { await fromChat(handed); return; } catch (err) { status(err.message, "error"); } }
    if (handed) { show("make"); return; }
    if (parts[1] && signedIn) return open(parts[1], parts[0]);
    show(parts[0] === "make" ? "make" : "projects");
  }
  document.addEventListener("DOMContentLoaded", start);
  window.ResileosStudio = { open: open, make: make };
})();
