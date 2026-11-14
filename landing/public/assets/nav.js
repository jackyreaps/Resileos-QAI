/* One short nav for every page: Chat, Studio, Pricing, Account (or Sign in),
 * and Admin only when /api/session/me says this account is an admin.
 * Marketing pages fill their existing #nav-menu. App pages (chat, studio)
 * get a slim strip. The admin link is a convenience only: every admin
 * page and API call is checked on the server. */
(function () {
  "use strict";
  var path = (location.pathname || "/").replace(/\.html$/, "").replace(/\/+$/, "") || "/";

  function links(me) {
    var out = [
      ["/chat", "Chat"],
      ["/studio", "Studio"],
      ["/pricing", "Pricing"],
      me && me.signed_in ? ["/account", "Account"] : ["/login", "Sign in"],
    ];
    if (me && me.admin) out.push(["/admin", "Admin"]);
    return out;
  }
  function current(href) {
    if (href === "/admin") return path.indexOf("/admin") === 0;
    return path === href;
  }
  function fill(menu, me, cls) {
    menu.replaceChildren();
    links(me).forEach(function (pair) {
      var a = document.createElement("a");
      a.href = pair[0];
      a.textContent = pair[1];
      if (pair[0] === "/chat" && cls) a.className = cls;
      if (pair[0] === "/admin") a.setAttribute("data-admin-link", "");
      if (current(pair[0])) a.setAttribute("aria-current", "page");
      menu.appendChild(a);
    });
  }
  function strip() {
    if (document.querySelector(".site-strip")) return document.getElementById("site-strip-menu");
    var nav = document.createElement("nav");
    nav.className = "site-strip";
    nav.setAttribute("aria-label", "Primary");
    var inner = document.createElement("div");
    inner.className = "site-strip-inner";
    var logo = document.createElement("a");
    logo.className = "site-strip-logo";
    logo.href = "/";
    logo.textContent = "Resileos";
    var toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "site-strip-toggle";
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-controls", "site-strip-menu");
    toggle.setAttribute("aria-label", "Open menu");
    for (var i = 0; i < 3; i++) toggle.appendChild(document.createElement("span"));
    var menu = document.createElement("div");
    menu.className = "site-strip-links";
    menu.id = "site-strip-menu";
    toggle.addEventListener("click", function () {
      var open = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", String(open));
      toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
      menu.classList.toggle("open", open);
    });
    menu.addEventListener("click", function (event) {
      if (event.target.closest("a")) {
        menu.classList.remove("open");
        toggle.setAttribute("aria-expanded", "false");
      }
    });
    inner.append(logo, toggle, menu);
    nav.appendChild(inner);
    document.body.insertBefore(nav, document.body.firstChild);
    return menu;
  }
  function render(me) {
    var menu = document.getElementById("nav-menu");
    if (menu) fill(menu, me, "nav-cta");
    else fill(strip(), me, "is-chat");
  }
  var cached = null;
  function session() {
    if (cached) return cached;
    if (window.ResileosAuth && window.ResileosAuth.me) cached = window.ResileosAuth.me();
    else {
      cached = fetch("/api/session/me", { credentials: "same-origin", cache: "no-store" })
        .then(function (r) { return r.json(); })
        .catch(function () { return { signed_in: false }; });
    }
    return cached;
  }
  window.ResileosNav = { links: links, render: render, session: session };
  function start() {
    render(null);
    session().then(function (me) { render(me || { signed_in: false }); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
