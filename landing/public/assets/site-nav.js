/* Thin site strip for /chat only.
   Marketing pages ship the same links in HTML. This file stays out of chat
   internals: it inserts one bar and does nothing once a thread is open. */
(function () {
  var path = (location.pathname || "/").replace(/\/+$/, "") || "/";
  if (path !== "/chat" && path !== "/chat.html") return;
  if (document.querySelector(".site-strip")) return;

  var links = [
    ["/", "Home"],
    ["/how-it-works", "How it works"],
    ["/kin", "Kin"],
    ["/pricing", "Pricing"],
    ["/login", "Sign in"],
    ["/account", "Account"],
    ["/chat", "Chat"]
  ];

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

  links.forEach(function (pair) {
    var a = document.createElement("a");
    a.href = pair[0];
    a.textContent = pair[1];
    if (pair[0] === "/chat") {
      a.className = "is-chat";
      a.setAttribute("aria-current", "page");
    }
    a.addEventListener("click", function () {
      menu.classList.remove("open");
      toggle.setAttribute("aria-expanded", "false");
    });
    menu.appendChild(a);
  });

  toggle.addEventListener("click", function () {
    var open = toggle.getAttribute("aria-expanded") !== "true";
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    menu.classList.toggle("open", open);
  });

  inner.appendChild(logo);
  inner.appendChild(toggle);
  inner.appendChild(menu);
  nav.appendChild(inner);
  document.body.insertBefore(nav, document.body.firstChild);
})();
