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
    const options = Object.assign({ credentials: "same-origin" }, opts || {});
    return fetch(url, options);
  }

  // Load public config (payment links, API base in code samples) only on
  // pages that show them, so other pages make no extra request.
  const needsConfig = document.querySelector("#link-builder, #link-team, #code-learn, #code-query, #code-chain");
  (needsConfig ? api("/api/config") : Promise.resolve(null))
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

  const form = document.getElementById("free-key-form");
  form?.addEventListener("submit", (e) => {
    e.preventDefault();
    window.location.href = "/login?next=/account";
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
          credentials: "same-origin",
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
      box.textContent = "Checking the plan…";
      api("/api/claim/" + encodeURIComponent(sid))
        .then(async (r) => {
          const data = await r.json().catch(() => ({}));
          if (!r.ok) {
            box.textContent = data.detail || "Plan not ready — refresh shortly.";
            box.className = "msg err";
            return;
          }
          box.textContent = data.attached
            ? "Plan attached. Opening account."
            : "Checkout recorded. Sign in with the same email.";
          box.className = "msg ok";
          window.location.assign(data.attached ? "/account" : "/login?next=/account");
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
  // Links are drawn by /assets/nav.js; close the mobile menu on any link click.
  menu?.addEventListener("click", (e) => {
    if (e.target.closest("a")) setMenu(false);
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

  // Decorative light sweeps. src is applied only when motion is allowed, so a
  // reduced-motion visit does not download the loop. These loops are site craft.
  if (!reduceMotion) {
    document.querySelectorAll("img.hero-motion[data-src]").forEach((img) => {
      img.addEventListener("error", () => img.remove());
      img.src = img.getAttribute("data-src");
    });
  }

  // Later hook for a real short hero or patron clip.
  // Put a video URL on the figure: data-video-src="/assets/motion/example.mp4"
  // Nothing is mounted unless that URL returns a video. Do not set a placeholder,
  // and do not describe the clip as something the engine generated.
  if (!reduceMotion) {
    document.querySelectorAll("[data-video-src]").forEach((fig) => {
      const src = (fig.getAttribute("data-video-src") || "").trim();
      if (!src) return;
      fetch(src, { method: "HEAD" })
        .then((res) => {
          if (!res.ok) return;
          const type = res.headers.get("content-type") || "";
          if (type && type.indexOf("video/") !== 0) return;
          const video = document.createElement("video");
          video.className = "hero-motion";
          video.src = src;
          video.muted = true;
          video.loop = true;
          video.autoplay = true;
          video.playsInline = true;
          video.setAttribute("aria-hidden", "true");
          fig.appendChild(video);
        })
        .catch(() => {});
    });
  }

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
