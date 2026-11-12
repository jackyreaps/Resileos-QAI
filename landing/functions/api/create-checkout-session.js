import { detail, json, priceEnvName, siteUrl } from "../_lib.js";

function requestOrigin(request, env) {
  const fallback = siteUrl(env).replace(/\/$/, "") || "https://resileosai.fun";
  try {
    const url = new URL(request.url);
    const host = url.host;
    if (
      host === "resileosai.fun" ||
      host === "www.resileosai.fun" ||
      host.endsWith(".pages.dev") ||
      host.startsWith("localhost") ||
      host.startsWith("127.0.0.1")
    ) {
      return url.origin;
    }
  } catch {
    /* use the configured site */
  }
  return fallback;
}

function successTarget(request, env) {
  const origin = requestOrigin(request, env);
  const configured = (env.STRIPE_SUCCESS_URL || "").trim();
  if (!configured) return `${origin}/chat?checkout=success`;
  try {
    const url = new URL(configured, origin);
    const host = url.host;
    if (
      host === "resileosai.fun" ||
      host === "www.resileosai.fun" ||
      host.endsWith(".pages.dev") ||
      host.startsWith("localhost") ||
      host.startsWith("127.0.0.1")
    ) {
      return `${origin}/chat?checkout=success`;
    }
  } catch {
    /* keep a custom success URL */
  }
  return configured;
}

export async function onRequestPost({ request, env }) {
  if (!env.STRIPE_SECRET_KEY) {
    return detail(
      "Stripe is not configured. Set STRIPE_SECRET_KEY, or use a Payment Link from /api/config.",
      503
    );
  }
  let body = {};
  try {
    body = await request.json();
  } catch {
    return detail("Invalid JSON body", 400);
  }
  const plan = body.plan;
  const priceKey = priceEnvName(plan);
  if (!priceKey) return detail("plan must be builder, founding_builder, or team", 400);
  const priceId = env[priceKey];
  if (!priceId) return detail(`Missing ${priceKey}. Create the Stripe Price and set the env var.`, 503);

  const success = successTarget(request, env);
  const cancel = env.STRIPE_CANCEL_URL || `${requestOrigin(request, env)}/#pricing`;
  const params = new URLSearchParams();
  params.set("mode", "subscription");
  params.set("line_items[0][price]", priceId);
  params.set("line_items[0][quantity]", "1");
  params.set("success_url", `${success}${success.includes("?") ? "&" : "?"}session_id={CHECKOUT_SESSION_ID}`);
  params.set("cancel_url", cancel);
  params.set("metadata[plan]", plan);
  params.set("allow_promotion_codes", "true");
  if (typeof body.email === "string" && body.email.includes("@")) {
    params.set("customer_email", body.email.trim());
  }

  const res = await fetch("https://api.stripe.com/v1/checkout/sessions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: params,
  });
  const data = await res.json();
  if (!res.ok) {
    return detail(typeof data.error?.message === "string" ? data.error.message : "Stripe error", 502);
  }
  return json({ id: data.id, url: data.url });
}
