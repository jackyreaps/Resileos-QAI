/* Studio: pick Picture or Short clip, describe it or use your photos,
 * choose a simple style, then make it. Requests go through the signed
 * session proxy; no key ever reaches this page. If nothing can be made,
 * the page says so. It never shows a stand-in result. */
(function () {
  "use strict";
  var API = "/api/session/v1";
  var MAX_FRAMES = 12;
  var MAX_SIDE = 40;
  var LENGTH_SECONDS = { short: 2, medium: 4, long: 6 };
  var LENGTH_WORDS = { short: "about 2 seconds", medium: "about 4 seconds", long: "about 6 seconds" };
  var MOTION_WORDS = { still: "almost no motion", gentle: "gentle motion", lively: "lively motion" };

  var csrf = "";
  var signedIn = false;
  var frames = null;
  var rgbFrames = null;
  var playTimer = null;
  var handoffPrompt = "";

  function $(id) { return document.getElementById(id); }
  function picked(name) {
    var el = document.querySelector('input[name="' + name + '"]:checked');
    return el ? el.value : "";
  }
  function setMsg(text, kind) {
    var el = $("studio-msg");
    el.textContent = text || "";
    el.className = "msg" + (kind ? " " + kind : "");
  }

  function sync() {
    var type = picked("type");
    var source = picked("source");
    var clip = type === "clip";
    var upload = source === "upload";
    $("source-legend").textContent = clip ? "Describe it, or use your photos" : "Describe it, or start from a photo";
    $("upload-title").textContent = clip ? "Choose photos or a short video" : "Choose a photo";
    $("upload-desc").textContent = clip
      ? "Pick one photo to bring it to life, or 2 to 12 photos in order, or one short video. They stay in your browser until you press Make it."
      : "Studio makes color variations of it from its color code. It stays in your browser until you press Make it.";
    $("describe-wrap").hidden = upload;
    $("upload-wrap").hidden = !upload;
    $("upload").multiple = clip;
    $("upload").accept = clip ? "image/*,video/*" : "image/*";
    $("style-motion").hidden = !clip || upload;
    $("style-length").hidden = !clip;
    document.querySelectorAll('input[name="color"]').forEach(function (el) { el.disabled = upload; });
    if (upload) document.querySelector('input[name="color"][value="bw"]').checked = true;
    $("style-note").textContent = upload
      ? (clip ? "One photo becomes a moving clip in color. Two or more photos play in order, in black and white. Length sets how long it plays." : "You get four color variations that keep your photo's shapes.")
      : "";
    $("prompt").placeholder = clip ? "Waves rolling onto a beach at dusk" : "A red fox in fresh snow at sunrise";
    $("generate").textContent = clip ? "Make the clip" : "Make the picture";
  }

  function describedPrompt() {
    var text = $("prompt").value.trim();
    if (!text) return "";
    var style = [];
    if (picked("color") === "bw") style.push("black and white");
    if (picked("type") === "clip") {
      style.push(MOTION_WORDS[picked("motion")] || "gentle motion");
      style.push(LENGTH_WORDS[picked("length")] || "about 2 seconds");
    }
    return style.length ? text + ". Style: " + style.join(", ") + "." : text;
  }

  // ---- reading uploads: the same reader chat uses (assets/media.js) ----
  async function readUpload(files) {
    var list = Array.prototype.slice.call(files || []);
    if (!list.length) return null;
    var M = window.ResileosMedia;
    var video = list.find(function (f) { return /^video\//.test(f.type); });
    if (video) {
      var clip = await M.readVideo(video, MAX_SIDE);
      rgbFrames = clip.rgb;
      return clip.gray;
    }
    var images = list.filter(function (f) { return /^image\//.test(f.type); }).slice(0, MAX_FRAMES);
    if (!images.length) throw new Error("Pick photos or a short video.");
    var first = await M.readImage(images[0], MAX_SIDE);
    var out = [first.gray];
    var rgb = [first.rgb];
    for (var i = 1; i < images.length; i++) {
      var next = await M.readImage(images[i], MAX_SIDE, first.dims);
      out.push(next.gray);
      rgb.push(next.rgb);
    }
    rgbFrames = rgb;
    return out;
  }

  // ---- showing results ----
  function stopPlayback() {
    if (playTimer) clearInterval(playTimer);
    playTimer = null;
  }
  function drawFrame(canvas, frame, lo, hi) {
    if (Array.isArray(frame[0][0])) return window.ResileosMedia.drawFrame(canvas, frame);
    var h = frame.length, w = frame[0].length;
    var small = document.createElement("canvas");
    small.width = w;
    small.height = h;
    var sctx = small.getContext("2d");
    var img = sctx.createImageData(w, h);
    var span = hi - lo || 1;
    for (var y = 0; y < h; y++) {
      for (var x = 0; x < w; x++) {
        var v = Math.max(0, Math.min(255, Math.round(((Number(frame[y][x]) - lo) / span) * 255)));
        var i = (y * w + x) * 4;
        img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
        img.data[i + 3] = 255;
      }
    }
    sctx.putImageData(img, 0, 0);
    var ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(small, 0, 0, canvas.width, canvas.height);
  }
  function validFrames(list) {
    return Array.isArray(list) && list.length > 0 && list.every(function (f) {
      return Array.isArray(f) && f.length && Array.isArray(f[0]) && f[0].length;
    });
  }
  function range(list) {
    if (Array.isArray(list[0][0][0])) return [0, 1];
    var lo = Infinity, hi = -Infinity;
    list.forEach(function (f) { f.forEach(function (r) { r.forEach(function (v) { v = Number(v); if (v < lo) lo = v; if (v > hi) hi = v; }); }); });
    return [lo, hi];
  }
  function playPreview(list, seconds) {
    var media = $("result-media");
    var canvas = document.createElement("canvas");
    var w = list[0][0].length, h = list[0].length;
    canvas.width = 360;
    canvas.height = Math.round((360 * h) / w);
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", "Your clip, playing on a loop");
    media.replaceChildren(canvas);
    var r = range(list);
    var i = 0;
    var delay = Math.max(80, Math.round((seconds * 1000) / list.length));
    drawFrame(canvas, list[0], r[0], r[1]);
    stopPlayback();
    playTimer = setInterval(function () {
      i = (i + 1) % list.length;
      drawFrame(canvas, list[i], r[0], r[1]);
    }, delay);
    return { canvas: canvas, delay: delay, lo: r[0], hi: r[1] };
  }
  function downloadBlob(blob, name) {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }
  function recordClip(list, view) {
    return new Promise(function (resolve, reject) {
      if (typeof MediaRecorder === "undefined" || !view.canvas.captureStream) { reject(new Error("unsupported")); return; }
      var canvas = document.createElement("canvas");
      canvas.width = view.canvas.width;
      canvas.height = view.canvas.height;
      var stream = canvas.captureStream(30);
      var type = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"].find(function (t) { return MediaRecorder.isTypeSupported(t); });
      if (!type) { reject(new Error("unsupported")); return; }
      var chunks = [];
      var rec = new MediaRecorder(stream, { mimeType: type });
      rec.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
      rec.onstop = function () { resolve(new Blob(chunks, { type: "video/webm" })); };
      var i = 0;
      drawFrame(canvas, list[0], view.lo, view.hi);
      rec.start();
      var timer = setInterval(function () {
        i += 1;
        if (i >= list.length) { clearInterval(timer); rec.stop(); return; }
        drawFrame(canvas, list[i], view.lo, view.hi);
      }, view.delay);
    });
  }
  function filmstrip(list, view) {
    var w = list[0][0].length * 4, h = list[0].length * 4;
    var canvas = document.createElement("canvas");
    canvas.width = w * list.length;
    canvas.height = h;
    var ctx = canvas.getContext("2d");
    list.forEach(function (frame, i) {
      var c = document.createElement("canvas");
      c.width = w; c.height = h;
      drawFrame(c, frame, view.lo, view.hi);
      ctx.drawImage(c, i * w, 0);
    });
    return new Promise(function (resolve) { canvas.toBlob(resolve, "image/png"); });
  }
  function button(label, primary, onClick) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "btn " + (primary ? "btn-primary" : "btn-ghost");
    b.textContent = label;
    b.addEventListener("click", onClick);
    return b;
  }

  function fmt(value) {
    if (value === null || value === undefined) return "not measured";
    if (typeof value === "number") return Math.round(value * 1000) / 1000 + "";
    if (typeof value === "boolean") return value ? "yes" : "no";
    if (typeof value === "string") return value;
    return JSON.stringify(value);
  }
  function fillDetails(data, status) {
    var list = $("details-list");
    list.replaceChildren();
    function row(label, value) {
      if (value === undefined) return;
      var dt = document.createElement("dt");
      dt.textContent = label;
      var dd = document.createElement("dd");
      dd.textContent = fmt(value);
      list.append(dt, dd);
    }
    var d = data || {};
    row("HTTP status", status);
    row("Result status", d.status);
    row("Stage", d.stage);
    row("Verified", d.verified);
    row("Provider called", d.provider_called);
    var m = d.check_metrics || {};
    row("Motion coherence (Kuramoto R)", m.motion_phase_coherence);
    row("Moving transitions", m.moving_transitions);
    row("Shape counts per frame (Betti)", m.betti);
    row("Shapes stable (Betti)", m.betti_stable);
    var badge = d.badge || {};
    row("Energy", badge.energy !== undefined ? badge.energy : d.energy);
    row("Consistency score", badge.consistency_score);
    row("Chroma", d.chroma);
    var bits = d.bits_per_frame || {};
    row("Frames", bits.frames);
    row("Bits per frame (mean)", bits.mean_delta);
    row("Note", d.note || d.detail);
  }

  function showResult(kind, data, status, sent) {
    var box = $("result");
    var title = $("result-title");
    var text = $("result-text");
    var media = $("result-media");
    var actions = $("result-actions");
    stopPlayback();
    media.replaceChildren();
    actions.replaceChildren();
    box.hidden = false;
    fillDetails(data, status);
    var d = data || {};
    var noun = kind === "clip" ? "clip" : "picture";
    var url = typeof d.url === "string" && /^https?:\/\//.test(d.url) ? d.url : "";
    // No generator: the API says UNAVAILABLE, or that this path produces no media.
    var unavailable = String(d.status || "").toUpperCase() === "UNAVAILABLE" || d.produces_video === false;

    if (url) {
      title.textContent = "Your " + noun + " is ready";
      text.textContent = d.verified ? "Checked and ready to download." : "Ready to download. It hasn't been checked yet.";
      var el;
      if (/\.(png|jpe?g|webp|gif)(\?|$)/i.test(url)) {
        el = document.createElement("img");
        el.alt = "Your " + noun;
      } else {
        el = document.createElement("video");
        el.controls = true;
        el.loop = true;
        el.playsInline = true;
      }
      el.src = url;
      media.appendChild(el);
      var a = document.createElement("a");
      a.className = "btn btn-primary";
      a.href = url;
      a.download = "";
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = "Download";
      actions.appendChild(a);
      return;
    }

    if (Array.isArray(d.variations) && d.variations.length) {
      title.textContent = "Your variations are ready";
      text.textContent = "Made from your photo's color code. Pick one to download.";
      var grid = document.createElement("div");
      grid.className = "variation-grid";
      d.variations.forEach(function (v, i) {
        var m = v.matrix || v;
        var fig = document.createElement("figure");
        var c = document.createElement("canvas");
        c.width = 180;
        c.height = Math.round((180 * m.length) / m[0].length);
        c.setAttribute("role", "img");
        c.setAttribute("aria-label", "Variation " + (i + 1));
        window.ResileosMedia.drawFrame(c, m);
        var dl = button("Download", false, function () {
          c.toBlob(function (blob) { downloadBlob(blob, "resileos-variation-" + (i + 1) + ".png"); }, "image/png");
        });
        fig.append(c, dl);
        grid.appendChild(fig);
      });
      media.appendChild(grid);
      return;
    }

    if (validFrames(d.frames) && d.made) {
      var secs = LENGTH_SECONDS[picked("length")] || 2;
      var v2 = playPreview(d.frames, secs);
      title.textContent = "Your clip is ready";
      text.textContent = "Made from your photo's color code, stepped over time. Download it below.";
      actions.appendChild(button("Download clip", true, async function (ev) {
        var btn = ev.currentTarget;
        btn.disabled = true;
        btn.textContent = "Preparing…";
        try {
          downloadBlob(await recordClip(d.frames, v2), "resileos-clip.webm");
        } catch (err) {
          downloadBlob(await window.ResileosMedia.filmstrip(d.frames), "resileos-clip-frames.png");
          setMsg("This browser can't save video, so the frames were saved as one picture instead.");
        }
        btn.disabled = false;
        btn.textContent = "Download clip";
      }));
      actions.appendChild(button("Download frames (PNG)", false, async function () {
        downloadBlob(await window.ResileosMedia.filmstrip(d.frames), "resileos-clip-frames.png");
      }));
      return;
    }

    if (sent.frames && validFrames(d.preview)) {
      var seconds = LENGTH_SECONDS[picked("length")] || 2;
      var view = playPreview(d.preview, seconds);
      title.textContent = "Your clip is ready";
      text.textContent = "Made from your " + sent.frames + " frames, in black and white. Download it below.";
      actions.appendChild(button("Download clip", true, async function (ev) {
        var btn = ev.currentTarget;
        btn.disabled = true;
        btn.textContent = "Preparing…";
        try {
          downloadBlob(await recordClip(d.preview, view), "resileos-clip.webm");
        } catch (err) {
          downloadBlob(await filmstrip(d.preview, view), "resileos-clip-frames.png");
          setMsg("This browser can't save video, so the frames were saved as one picture instead.");
        }
        btn.disabled = false;
        btn.textContent = "Download clip";
      }));
      actions.appendChild(button("Download frames (PNG)", false, async function () {
        downloadBlob(await filmstrip(d.preview, view), "resileos-clip-frames.png");
      }));
      return;
    }

    title.textContent = "Nothing was made";
    if (unavailable) {
      text.textContent = kind === "clip"
        ? "This site doesn't have a video maker connected yet, so Studio won't pretend to make one. You can still turn your own photos into a clip: choose \u201cStart from my photos\u201d."
        : "This site doesn't have a picture maker connected yet, so Studio won't pretend to make one. Please try again later.";
    } else {
      text.textContent = "Studio couldn't make this " + noun + ". Try a different description or other photos.";
    }
  }

  async function generate(event) {
    event.preventDefault();
    var type = picked("type");
    var upload = picked("source") === "upload";
    var path = type === "clip" ? "/studio/video" : "/studio/forge/video";
    var body = { stage: "draft" };
    var sent = {};
    if (upload && type === "image") {
      if (!frames || !frames.length) {
        setMsg("Choose a photo first.", "err");
        $("upload").focus();
        return;
      }
      path = "/studio/variations";
      body = { matrix: (rgbFrames && rgbFrames[0]) || frames[0], n: 4 };
    } else if (upload && frames && frames.length === 1) {
      path = "/studio/clip-from-picture";
      body = { matrix: (rgbFrames && rgbFrames[0]) || frames[0], frames_out: { short: 12, medium: 18, long: 24 }[picked("length")] || 12 };
    } else if (upload) {
      if (!frames || frames.length < 2) {
        setMsg("Choose a photo, a few photos, or one short video first.", "err");
        $("upload").focus();
        return;
      }
      body.prompt = handoffPrompt || "Clip from my photos";
      body.frames = frames;
      sent.frames = frames.length;
    } else {
      var prompt = describedPrompt();
      if (!prompt) {
        setMsg("Describe what you want first.", "err");
        $("prompt").focus();
        return;
      }
      body.prompt = prompt.slice(0, 2000);
    }
    var go = $("generate");
    go.disabled = true;
    setMsg(type === "clip" ? "Making your clip…" : "Making your picture…");
    try {
      var headers = { "content-type": "application/json" };
      if (csrf) headers["x-csrf-token"] = csrf;
      var res = await fetch(API + path, { method: "POST", credentials: "same-origin", headers: headers, body: JSON.stringify(body) });
      var data = await res.json().catch(function () { return {}; });
      if (res.status === 401) {
        setMsg("");
        var box = $("studio-msg");
        box.className = "msg err";
        box.textContent = "Please sign in to use Studio. ";
        var link = document.createElement("a");
        link.href = "/login?next=" + encodeURIComponent("/studio");
        link.textContent = "Sign in";
        box.appendChild(link);
        return;
      }
      if (!res.ok) {
        var detail = typeof data.detail === "string" ? data.detail : "";
        setMsg(detail || "Studio couldn't finish that. Please try again.", "err");
        fillDetails(data, res.status);
        return;
      }
      setMsg("");
      showResult(type, data, res.status, sent);
      $("result").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      setMsg("Couldn't reach Studio. Check your connection and try again.", "err");
    } finally {
      go.disabled = false;
    }
  }

  async function onUpload() {
    var summary = $("upload-summary");
    frames = null;
    rgbFrames = null;
    summary.textContent = "Reading…";
    try {
      frames = await readUpload($("upload").files);
      summary.textContent = frames && frames.length
        ? (frames.length === 1 ? "Photo ready." : frames.length + " frames ready.")
        : "Pick a photo or a short video.";
    } catch (err) {
      frames = null;
      summary.textContent = err && err.message ? err.message : "Those files could not be read.";
    }
  }

  function start() {
    var params = new URLSearchParams(location.search);
    var type = params.get("type");
    if (type === "clip" || type === "image") {
      document.querySelector('input[name="type"][value="' + type + '"]').checked = true;
    }
    var prompt = params.get("prompt");
    if (prompt) $("prompt").value = prompt.slice(0, 1500);
    if (params.get("source") === "upload" && type === "clip") {
      document.querySelector('input[name="source"][value="upload"]').checked = true;
    }
    document.querySelectorAll('input[name="type"], input[name="source"]').forEach(function (el) {
      el.addEventListener("change", sync);
    });
    $("upload").addEventListener("change", onUpload);
    // From chat ("make a clip / variation from this") or from Files.
    var handed = params.get("from") === "chat" && window.ResileosMedia ? window.ResileosMedia.takeHandoff() : null;
    // Signed-in: the Studio app turns the handoff into a project (studio-app.js).
    if (handed) window.__studioHandoff = handed;
    if (handed && Array.isArray(handed.frames) && handed.frames.length) {
      var kind = handed.type === "clip" ? "clip" : "image";
      document.querySelector('input[name="type"][value="' + kind + '"]').checked = true;
      document.querySelector('input[name="source"][value="upload"]').checked = true;
      frames = handed.frames;
      rgbFrames = Array.isArray(handed.rgb) && handed.rgb.length ? handed.rgb : null;
      handoffPrompt = String(handed.prompt || "").slice(0, 500);
      if (handoffPrompt) $("prompt").value = handoffPrompt;
      $("upload-summary").textContent = "From chat: " + (handed.name || "your attachment") + (frames.length > 1 ? " (" + frames.length + " frames)" : "") + ".";
    }
    var savedId = params.get("file");
    if (savedId && /^[a-f0-9]{32}$/.test(savedId) && window.ResileosMedia) {
      $("upload-summary").textContent = "Opening your file…";
      window.ResileosMedia.fromSavedFile(savedId, params.get("name") || "file").then(async function (file) {
        var isClip = /^video\//.test(file.type) || type === "clip";
        document.querySelector('input[name="type"][value="' + (isClip ? "clip" : "image") + '"]').checked = true;
        document.querySelector('input[name="source"][value="upload"]').checked = true;
        sync();
        frames = await readUpload([file]);
        $("upload-summary").textContent = "From your files: " + file.name + ".";
      }).catch(function () { $("upload-summary").textContent = "That file couldn't be opened."; });
    }
    $("studio-form").addEventListener("submit", generate);
    sync();
    var me = window.ResileosNav ? window.ResileosNav.session() : fetch("/api/session/me", { credentials: "same-origin" }).then(function (r) { return r.json(); });
    Promise.resolve(me).then(function (account) {
      csrf = (account && account.csrf) || "";
      signedIn = Boolean(account && account.signed_in);
      if (!signedIn) setMsg("You can try Studio without an account. Sign in to keep going after the free tries.");
    }).catch(function () { /* the page still works for the free trial */ });
  }

  window.ResileosStudio = { describedPrompt: describedPrompt, validFrames: validFrames };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
