/* My files: list, upload, download, delete, and reuse in chat or Studio. */
(function () {
  "use strict";
  var API = "/api/session/v1/files";
  var csrf = "";
  function $(id) { return document.getElementById(id); }
  function setMsg(text, kind) { var el = $("files-msg"); el.textContent = text || ""; el.className = "msg" + (kind ? " " + kind : ""); }
  function mb(n) { return n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB"; }
  var ICON = { image: "▣", clip: "▶", text: "¶", lean: "λ" };

  function row(f) {
    var li = document.createElement("li");
    li.className = "file-row";
    var icon = document.createElement("span");
    icon.className = "file-icon";
    icon.textContent = ICON[f.kind] || "•";
    var info = document.createElement("div");
    var name = document.createElement("div");
    name.className = "file-name";
    name.textContent = f.name;
    var meta = document.createElement("div");
    meta.className = "file-meta";
    meta.textContent = mb(f.size || 0) + " · " + new Date(f.created_at).toLocaleDateString();
    info.append(name, meta);
    var actions = document.createElement("div");
    actions.className = "file-actions";
    var q = "file=" + encodeURIComponent(f.id) + "&name=" + encodeURIComponent(f.name);
    var chat = document.createElement("a");
    chat.href = "/chat?" + q;
    chat.textContent = "Use in chat";
    actions.appendChild(chat);
    if (f.kind === "image" || f.kind === "clip") {
      var studio = document.createElement("a");
      studio.href = "/studio?" + q + "&type=" + (f.kind === "clip" ? "clip" : "image");
      studio.textContent = "Use in Studio";
      actions.appendChild(studio);
    }
    var dl = document.createElement("a");
    dl.href = API + "/" + encodeURIComponent(f.id);
    dl.setAttribute("download", f.name);
    dl.textContent = "Download";
    actions.appendChild(dl);
    var del = document.createElement("button");
    del.type = "button";
    del.className = "danger";
    del.textContent = "Delete";
    del.addEventListener("click", async function () {
      if (!window.confirm("Delete " + f.name + "?")) return;
      var res = await fetch(API + "/" + encodeURIComponent(f.id), { method: "DELETE", credentials: "same-origin", headers: { "x-csrf-token": csrf } });
      var data = await res.json().catch(function () { return {}; });
      if (!res.ok) { setMsg(typeof data.detail === "string" ? data.detail : "Couldn't delete that file.", "err"); return; }
      setMsg("Deleted " + f.name + ".");
      load();
    });
    actions.appendChild(del);
    li.append(icon, info, actions);
    return li;
  }

  async function load() {
    var list = $("files-list");
    var res = await fetch(API, { credentials: "same-origin" });
    var data = await res.json().catch(function () { return {}; });
    list.replaceChildren();
    if (!res.ok) { setMsg(typeof data.detail === "string" ? data.detail : "Couldn't load your files.", "err"); return; }
    var files = data.files || [];
    if (!files.length) {
      var empty = document.createElement("li");
      empty.className = "files-empty";
      empty.textContent = "No files yet. Upload one here, or attach something in chat.";
      list.appendChild(empty);
    }
    files.forEach(function (f) { list.appendChild(row(f)); });
    var lim = data.limits || {};
    $("files-usage").textContent = mb(data.used || 0) + " of " + mb(lim.max_total || 104857600) + " used";
  }

  async function upload(fileList) {
    var files = Array.prototype.slice.call(fileList || []);
    for (var i = 0; i < files.length; i++) {
      setMsg("Uploading " + files[i].name + "…");
      try {
        await window.ResileosMediaSave(files[i]);
      } catch (err) {
        setMsg(err.message, "err");
        await load();
        return;
      }
    }
    setMsg(files.length === 1 ? "Uploaded." : "Uploaded " + files.length + " files.");
    await load();
  }

  window.ResileosMediaSave = async function (file) {
    var form = new FormData();
    form.append("file", file, file.name);
    var res = await fetch(API, { method: "POST", credentials: "same-origin", headers: { "x-csrf-token": csrf }, body: form });
    var data = await res.json().catch(function () { return {}; });
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Couldn't upload " + file.name + ".");
    return data;
  };

  async function start() {
    var me = await (window.ResileosAuth ? window.ResileosAuth.me() : Promise.resolve({ signed_in: false }));
    if (!me || !me.signed_in) {
      location.assign("/login?next=/files");
      return;
    }
    csrf = me.csrf || "";
    $("files-upload").addEventListener("change", function (e) { upload(e.target.files).finally(function () { e.target.value = ""; }); });
    load().catch(function () { setMsg("Couldn't load your files.", "err"); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
