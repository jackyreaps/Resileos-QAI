/* One sign-in for every page: login, account, chat, and admin.
 * The session lives in an HttpOnly cookie; this file never sees a key or token. */
(function () {
  "use strict";
  var HINT = "resileos_pw_hint";
  var LAST = "resileos_last_email";

  function safeNext(value, fallback) {
    var next = typeof value === "string" ? value.trim() : "";
    var dflt = fallback === undefined ? "/account" : fallback;
    if (!next || next.charAt(0) !== "/" || next.indexOf("//") === 0 || next.indexOf("/\\") === 0) return dflt;
    if (next.indexOf("/api/") === 0 || next.indexOf("/login") === 0 || next.length > 200) return dflt;
    return next;
  }
  function normalize(email) {
    return String(email || "").trim().toLowerCase();
  }
  function looksLikeEmail(value) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalize(value));
  }
  function store(key, value) {
    try {
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
    } catch (err) { /* storage is optional */ }
  }
  function read(key) {
    try { return localStorage.getItem(key) || ""; } catch (err) { return ""; }
  }
  async function me() {
    try {
      var res = await fetch("/api/session/me", { credentials: "same-origin", cache: "no-store" });
      var data = await res.json();
      return data && data.signed_in ? data : { signed_in: false };
    } catch (err) {
      return { signed_in: false, offline: true };
    }
  }
  async function post(path, body, csrf) {
    var headers = { "content-type": "application/json" };
    if (csrf) headers["x-csrf-token"] = csrf;
    var res;
    try {
      res = await fetch(path, {
        method: "POST",
        credentials: "same-origin",
        headers: headers,
        body: JSON.stringify(body || {}),
      });
    } catch (err) {
      return { res: { ok: false, status: 0 }, data: { detail: "Can't reach the site. Check your connection and try again." } };
    }
    var data = await res.json().catch(function () { return {}; });
    if (!res.ok && typeof data.detail !== "string") {
      data.detail = res.status === 503 ? "Sign-in email isn't available right now. Try again later." : "Something went wrong. Try again.";
    }
    return { res: res, data: data };
  }
  /* A hint, kept only in this browser, so the page can offer the password first.
   * The server never says whether an address has a password. */
  function rememberSignedIn(email, hasPassword) {
    var value = normalize(email);
    if (!value) return;
    store(LAST, value);
    if (hasPassword) store(HINT, value);
    else if (read(HINT) === value) store(HINT, null);
  }
  function hasPasswordHint(email) {
    var value = normalize(email);
    return Boolean(value) && read(HINT) === value;
  }
  function lastEmail() {
    return read(LAST);
  }
  function loginUrl(next) {
    var path = safeNext(next || (location.pathname + location.search), "/account");
    return "/login?next=" + encodeURIComponent(path);
  }
  async function logout(csrf) {
    await post("/api/session/logout", {}, csrf);
  }
  window.ResileosAuth = {
    safeNext: safeNext,
    normalize: normalize,
    looksLikeEmail: looksLikeEmail,
    me: me,
    post: post,
    logout: logout,
    loginUrl: loginUrl,
    rememberSignedIn: rememberSignedIn,
    hasPasswordHint: hasPasswordHint,
    lastEmail: lastEmail,
  };
})();
