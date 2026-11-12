(() => {
  const billingBase = (window.RESILEOS_BILLING || "").replace(/\/$/, "");

  // Tabs
  const tabs = document.querySelectorAll(".tab");
  const panels = document.querySelectorAll(".codebox[data-panel]");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const id = tab.dataset.tab;
      tabs.forEach((t) => t.classList.toggle("active", t === tab));
      panels.forEach((p) => {
        p.hidden = p.dataset.panel !== id;
      });
    });
  });

  // Copy buttons
  document.querySelectorAll(".copy").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.copy;
      const pre = document.getElementById("code-" + id);
      if (!pre) return;
      try {
        await navigator.clipboard.writeText(pre.textContent);
        btn.textContent = "Copied";
        setTimeout(() => (btn.textContent = "Copy"), 1200);
      } catch {
        btn.textContent = "Select text";
      }
    });
  });

  function api(path, opts) {
    const url = (billingBase || "") + path;
    return fetch(url, opts);
  }

  // Load public config (payment links, etc.)
  api("/api/config")
    .then((r) => (r.ok ? r.json() : null))
    .then((cfg) => {
      if (!cfg) return;
      const b = cfg.plans?.builder?.payment_link;
      const t = cfg.plans?.team?.payment_link;
      const lb = document.getElementById("link-builder");
      const lt = document.getElementById("link-team");
      if (b && lb) {
        lb.href = b;
        lb.hidden = false;
      }
      if (t && lt) {
        lt.href = t;
        lt.hidden = false;
      }
      if (cfg.api_base_url) {
        document.querySelectorAll("#code-learn, #code-query, #code-chain").forEach((pre) => {
          pre.textContent = pre.textContent.replaceAll(
            "https://api.yourdomain.dev/api/v1",
            cfg.api_base_url
          );
        });
      }
    })
    .catch(() => {});

  // Free key form
  const form = document.getElementById("free-key-form");
  const msg = document.getElementById("free-key-msg");
  const reveal = document.getElementById("key-reveal");
  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    msg.textContent = "Minting…";
    msg.className = "msg";
    reveal.classList.remove("show");
    const email = document.getElementById("email").value.trim();
    const name = document.getElementById("name").value.trim() || "free";
    try {
      const res = await api("/api/free-key", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email || null, name }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        msg.textContent = data.detail || "Could not issue key.";
        msg.className = "msg err";
        return;
      }
      msg.textContent = "Key issued. Copy it now — shown once.";
      msg.className = "msg ok";
      reveal.classList.add("show");
      reveal.replaceChildren();
      const keyLabel = document.createElement("div");
      const keyStrong = document.createElement("strong");
      keyStrong.textContent = "X-API-Key";
      keyLabel.appendChild(keyStrong);
      const keyLine = document.createElement("div");
      keyLine.textContent = data.api_key || "";
      const baseLabel = document.createElement("div");
      baseLabel.style.marginTop = "8px";
      const baseStrong = document.createElement("strong");
      baseStrong.textContent = "Base URL";
      baseLabel.appendChild(baseStrong);
      const baseLine = document.createElement("div");
      baseLine.textContent = data.base_url || "";
      const note = document.createElement("div");
      note.style.marginTop = "8px";
      note.style.color = "#8b97b0";
      note.textContent = data.note || "";
      const demo = document.createElement("div");
      demo.style.marginTop = "8px";
      demo.style.color = "#f0b429";
      demo.textContent = "demo_namespace: " + (data.demo_namespace || "coming_soon");
      const open = document.createElement("a");
      open.href = "/chat";
      open.className = "btn btn-primary";
      open.style.marginTop = "12px";
      open.textContent = "Open chat";
      reveal.append(keyLabel, keyLine, baseLabel, baseLine, note, demo, open);
      try {
        if (data.api_key) localStorage.setItem("resileos_api_key", data.api_key);
        if (data.base_url) localStorage.setItem("resileos_api_url", data.base_url);
      } catch (err) { /* the key is still on the page once */ }
      // Prefer server-provided curls if present
      if (data.quickstart) {
        if (data.quickstart.learn)
          document.getElementById("code-learn").textContent = data.quickstart.learn;
        if (data.quickstart.query)
          document.getElementById("code-query").textContent = data.quickstart.query;
        if (data.quickstart.chain)
          document.getElementById("code-chain").textContent = data.quickstart.chain;
      }
    } catch (err) {
      msg.textContent =
        "Billing API unreachable. Start api/server.py or set window.RESILEOS_BILLING.";
      msg.className = "msg err";
    }
  });

  // Stripe checkout buttons
  const checkoutMsg = document.getElementById("checkout-msg");
  document.querySelectorAll("[data-checkout]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const plan = btn.getAttribute("data-checkout");
      checkoutMsg.textContent = "Opening Stripe Checkout…";
      checkoutMsg.className = "msg";
      try {
        const res = await api("/api/create-checkout-session", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ plan }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          // Fallback: payment link if present
          const link =
            plan === "builder"
              ? document.getElementById("link-builder")
              : document.getElementById("link-team");
          if (link && !link.hidden && link.href && link.href !== "#") {
            checkoutMsg.textContent =
              (data.detail || "Checkout API unavailable.") +
              " Opening Payment Link fallback…";
            window.location.href = link.href;
            return;
          }
          checkoutMsg.textContent =
            typeof data.detail === "string"
              ? data.detail
              : "Stripe not configured yet. See DEPLOY.md.";
          checkoutMsg.className = "msg err";
          return;
        }
        if (data.url) window.location.href = data.url;
      } catch {
        checkoutMsg.textContent = "Could not reach billing API.";
        checkoutMsg.className = "msg err";
      }
    });
  });

  // Claim key after Checkout success
  const params = new URLSearchParams(location.search);
  if (params.get("checkout") === "success") {
    const sid = params.get("session_id");
    const box = document.getElementById("checkout-msg");
    if (sid && box) {
      box.textContent = "Retrieving your key…";
      api("/api/claim/" + encodeURIComponent(sid))
        .then(async (r) => {
          const data = await r.json().catch(() => ({}));
          if (!r.ok) {
            box.textContent = data.detail || "Key not ready — refresh shortly.";
            box.className = "msg err";
            return;
          }
          try {
            if (data.api_key) localStorage.setItem("resileos_api_key", data.api_key);
            if (data.base_url) localStorage.setItem("resileos_api_url", data.base_url);
          } catch (err) {
            box.className = "msg err";
            box.replaceChildren();
            const line = document.createElement("div");
            line.textContent = "This browser could not store the paid key. Copy it, then open chat.";
            const code = document.createElement("code");
            code.textContent = data.api_key || "";
            const open = document.createElement("a");
            open.href = "/chat";
            open.textContent = "Open chat";
            box.append(line, document.createElement("br"), code, document.createElement("br"), open);
            return;
          }
          window.location.assign("/chat");
        })
        .catch(() => {
          box.textContent = "Claim failed — webhook may still be processing.";
          box.className = "msg err";
        });
    }
  }

  // Mobile nav
  const toggle = document.querySelector(".nav-toggle");
  const menu = document.getElementById("nav-menu");
  function setMenu(open) {
    if (!toggle || !menu) return;
    toggle.setAttribute("aria-expanded", String(open));
    menu.classList.toggle("open", open);
    document.body.classList.toggle("nav-open", open);
  }
  toggle?.addEventListener("click", () => {
    setMenu(toggle.getAttribute("aria-expanded") !== "true");
  });
  menu?.querySelectorAll("a").forEach((a) => {
    a.addEventListener("click", () => setMenu(false));
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") setMenu(false);
  });

  // Active section highlight
  const navAnchors = Array.from(document.querySelectorAll(".nav-links a[href^='#']"))
    .filter((a) => a.getAttribute("href") !== "#start" && a.getAttribute("href") !== "#top");
  const watched = navAnchors
    .map((a) => {
      const id = (a.getAttribute("href") || "").slice(1);
      return { a, el: document.getElementById(id) };
    })
    .filter((x) => x.el);
  if (watched.length && "IntersectionObserver" in window) {
    const io = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (!visible) return;
        navAnchors.forEach((a) => a.classList.toggle("is-active", a.getAttribute("href") === "#" + visible.target.id));
      },
      { rootMargin: "-25% 0px -55% 0px", threshold: [0.1, 0.25, 0.5] }
    );
    watched.forEach(({ el }) => io.observe(el));
  }

  // Tab ARIA
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-selected", tab.classList.contains("active") ? "true" : "false");
  });
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.setAttribute("aria-selected", t === tab ? "true" : "false"));
    });
  });

  // Motion: Lenis, reveal, card glow, figurehead parallax
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!reduceMotion) {
    document.documentElement.classList.add("js-motion");

    if (typeof Lenis === "function") {
      const lenis = new Lenis({ lerp: 0.12, wheelMultiplier: 0.92, smoothWheel: true });
      function raf(time) {
        lenis.raf(time);
        requestAnimationFrame(raf);
      }
      requestAnimationFrame(raf);
      document.documentElement.classList.add("lenis");
    }

    const revealIo = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-in");
          revealIo.unobserve(entry.target);
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" }
    );
    const revealables = document.querySelectorAll(
      "#titanos, #structure, #pantheon, #kin, .hierarchy, .titanos-figure, .pantheon-card, .patron, section .card, .demi-card, .price-card"
    );
    revealables.forEach((el, i) => {
      el.classList.add("reveal");
      el.style.transitionDelay = ((i % 10) * 0.045).toFixed(3) + "s";
      revealIo.observe(el);
    });

    document.querySelectorAll(".card, .pantheon-card, .price-card").forEach((card) => {
      card.addEventListener("pointermove", (e) => {
        const r = card.getBoundingClientRect();
        card.style.setProperty("--mx", e.clientX - r.left + "px");
        card.style.setProperty("--my", e.clientY - r.top + "px");
      });
    });

    const titanImg = document.querySelector(".titanos-figure img");
    const titanFrame = document.querySelector(".titanos-figure");
    if (titanImg && titanFrame) {
      let ticking = false;
      const shift = () => {
        ticking = false;
        const r = titanFrame.getBoundingClientRect();
        const mid = r.top + r.height / 2 - window.innerHeight / 2;
        const y = Math.max(-28, Math.min(28, mid * -0.07));
        titanImg.style.transform = "translate3d(0," + y.toFixed(1) + "px,0) scale(1.05)";
      };
      window.addEventListener(
        "scroll",
        () => {
          if (!ticking) {
            ticking = true;
            requestAnimationFrame(shift);
          }
        },
        { passive: true }
      );
      shift();
    }
  }

})();
