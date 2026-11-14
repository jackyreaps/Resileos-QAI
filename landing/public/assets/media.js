/* Shared upload reading for chat and Studio. Everything happens in the
 * browser: pictures and clips are shrunk to small pixel grids, text files
 * are read as text. The server perceives these grids and text; it never
 * receives the original file unless you save it to Files. */
(function () {
  "use strict";
  var MAX_SIDE = 48;
  var MAX_FRAMES = 12;
  var MAX_TEXT = 20000;
  var TEXT_EXT = /\.(txt|md|csv|json|py|lean|tex|log|yaml|yml|toml)$/i;

  function kindOf(file) {
    var name = String(file.name || "");
    if (/\.lean$/i.test(name)) return "lean";
    if (/^image\//.test(file.type)) return "image";
    if (/^video\//.test(file.type)) return "clip";
    if (/^text\//.test(file.type) || TEXT_EXT.test(name) || file.type === "application/json") return "text";
    return "file";
  }

  function size(w, h, side) {
    var scale = (side || MAX_SIDE) / Math.max(w, h, 1);
    if (scale > 1) scale = 1;
    return { w: Math.max(4, Math.round(w * scale)), h: Math.max(4, Math.round(h * scale)) };
  }

  function grid(source, sw, sh, dims) {
    var canvas = document.createElement("canvas");
    canvas.width = dims.w;
    canvas.height = dims.h;
    var ctx = canvas.getContext("2d", { willReadFrequently: true });
    var target = dims.w / dims.h;
    var cw = sw, ch = sh;
    if (sw / sh > target) cw = sh * target; else ch = sw / target;
    ctx.drawImage(source, (sw - cw) / 2, (sh - ch) / 2, cw, ch, 0, 0, dims.w, dims.h);
    var data = ctx.getImageData(0, 0, dims.w, dims.h).data;
    var rgb = [], gray = [];
    for (var y = 0; y < dims.h; y++) {
      var row = [], grow = [];
      for (var x = 0; x < dims.w; x++) {
        var i = (y * dims.w + x) * 4;
        var r = data[i] / 255, g = data[i + 1] / 255, b = data[i + 2] / 255;
        row.push([Math.round(r * 1000) / 1000, Math.round(g * 1000) / 1000, Math.round(b * 1000) / 1000]);
        grow.push(Math.round((0.299 * r + 0.587 * g + 0.114 * b) * 1000) / 1000);
      }
      rgb.push(row);
      gray.push(grow);
    }
    return { rgb: rgb, gray: gray };
  }

  function thumb(source, sw, sh) {
    var dims = size(sw, sh, 160);
    var canvas = document.createElement("canvas");
    canvas.width = dims.w;
    canvas.height = dims.h;
    canvas.getContext("2d").drawImage(source, 0, 0, dims.w, dims.h);
    try { return canvas.toDataURL("image/jpeg", 0.8); } catch (err) { return ""; }
  }

  function loadImage(blob) {
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(blob);
      var img = new Image();
      img.onload = function () { resolve({ img: img, url: url }); };
      img.onerror = function () { URL.revokeObjectURL(url); reject(new Error("That picture couldn't be opened.")); };
      img.src = url;
    });
  }

  async function readImage(file, side, dims) {
    var loaded = await loadImage(file);
    var w = loaded.img.naturalWidth, h = loaded.img.naturalHeight;
    var g = grid(loaded.img, w, h, dims || size(w, h, side));
    var out = { rgb: g.rgb, gray: g.gray, thumb: thumb(loaded.img, w, h), width: w, height: h };
    URL.revokeObjectURL(loaded.url);
    out.dims = dims || size(w, h, side);
    return out;
  }

  function readVideo(file, side) {
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(file);
      var video = document.createElement("video");
      video.muted = true;
      video.playsInline = true;
      video.preload = "auto";
      var rgb = [], gray = [], times = [], dims = null, poster = "";
      function fail() { URL.revokeObjectURL(url); reject(new Error("That video couldn't be read in this browser.")); }
      function next() {
        if (!times.length) {
          URL.revokeObjectURL(url);
          resolve({ rgb: rgb, gray: gray, thumb: poster, duration: video.duration });
          return;
        }
        video.currentTime = times.shift();
      }
      video.addEventListener("error", fail);
      video.addEventListener("loadedmetadata", function () {
        var duration = isFinite(video.duration) ? video.duration : 0;
        if (!duration || !video.videoWidth) { fail(); return; }
        dims = size(video.videoWidth, video.videoHeight, side || 40);
        var count = Math.min(MAX_FRAMES, Math.max(2, Math.round(duration * 3)));
        for (var i = 0; i < count; i++) times.push((duration * (i + 0.5)) / count);
        next();
      });
      video.addEventListener("seeked", function () {
        var g = grid(video, video.videoWidth, video.videoHeight, dims);
        rgb.push(g.rgb);
        gray.push(g.gray);
        if (!poster) poster = thumb(video, video.videoWidth, video.videoHeight);
        next();
      });
      video.src = url;
    });
  }

  /* One attachment ready for /api/session/v1/assist. */
  async function prepare(file) {
    var kind = kindOf(file);
    var base = { name: String(file.name || "file").slice(0, 200), type: file.type || "", size: file.size || 0, kind: kind };
    if (kind === "image") {
      var img = await readImage(file);
      return Object.assign(base, { matrix: img.rgb, gray: img.gray, thumb: img.thumb });
    }
    if (kind === "clip") {
      var clip = await readVideo(file);
      return Object.assign(base, { frames: clip.rgb, grayFrames: clip.gray, thumb: clip.thumb });
    }
    if (kind === "text" || kind === "lean") {
      var text = await file.text();
      return Object.assign(base, { text: text.slice(0, MAX_TEXT), truncated: text.length > MAX_TEXT });
    }
    return base;
  }

  /* What the server needs, without browser-only fields. */
  function wire(att) {
    var out = { name: att.name, type: att.type, size: att.size, kind: att.kind };
    if (att.file_id) out.file_id = att.file_id;
    if (att.matrix) out.matrix = att.matrix;
    if (att.frames) out.frames = att.frames;
    if (typeof att.text === "string") out.text = att.text;
    return out;
  }

  /* Hand an attachment to Studio ("make a clip / variation from this"). */
  function handoff(att, type) {
    var payload = { type: type || (att.kind === "clip" ? "clip" : "image"), name: att.name, thumb: att.thumb || "" };
    if (att.grayFrames) payload.frames = att.grayFrames;
    else if (att.gray) payload.frames = [att.gray];
    if (att.prompt) payload.prompt = att.prompt;
    try { sessionStorage.setItem("resileos_studio_handoff", JSON.stringify(payload)); } catch (err) { return false; }
    return true;
  }

  function takeHandoff() {
    try {
      var raw = sessionStorage.getItem("resileos_studio_handoff");
      sessionStorage.removeItem("resileos_studio_handoff");
      return raw ? JSON.parse(raw) : null;
    } catch (err) { return null; }
  }

  /* Fetch one of your saved files and turn it into a File object. */
  async function fromSavedFile(id, name, csrf) {
    var res = await fetch("/api/session/v1/files/" + encodeURIComponent(id), { credentials: "same-origin" });
    if (!res.ok) throw new Error("That file couldn't be opened.");
    var blob = await res.blob();
    var file = new File([blob], name || "file", { type: (blob.type || "").split(";")[0] });
    return file;
  }

  async function saveToFiles(file, csrf) {
    var form = new FormData();
    form.append("file", file, file.name);
    var headers = {};
    if (csrf) headers["x-csrf-token"] = csrf;
    var res = await fetch("/api/session/v1/files", { method: "POST", credentials: "same-origin", headers: headers, body: form });
    var data = await res.json().catch(function () { return {}; });
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Couldn't save that file.");
    return data;
  }

  window.ResileosMedia = {
    kindOf: kindOf,
    prepare: prepare,
    wire: wire,
    readImage: readImage,
    readVideo: readVideo,
    handoff: handoff,
    takeHandoff: takeHandoff,
    fromSavedFile: fromSavedFile,
    saveToFiles: saveToFiles,
    MAX_FRAMES: MAX_FRAMES,
  };
})();
