export const TIER_QUOTA = {
  free: { tier: "free", quota: 5000 },
  builder: { tier: "pro", quota: 100000 },
  founding_builder: { tier: "pro", quota: 100000 },
  team: { tier: "pro", quota: 500000 },
  org: { tier: "enterprise", quota: 0 },
};

export function json(data, status = 200, extra = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      ...extra,
    },
  });
}

export function detail(message, status) {
  return json({ detail: message }, status);
}

export async function sha256Hex(value) {
  const data = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function mintPlaintext() {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  const token = btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  return `rsk_${token}`;
}

export function clientIp(request) {
  return (
    request.headers.get("cf-connecting-ip") ||
    (request.headers.get("x-forwarded-for") || "").split(",")[0].trim() ||
    "unknown"
  );
}

export function siteUrl(env) {
  return env.RESILEOS_SITE_URL || "https://resileosai.fun";
}

export function apiBase(env) {
  return env.RESILEOS_API_BASE_URL || "https://api.yourdomain.dev/api/v1";
}

export function priceEnvName(plan) {
  return {
    builder: "STRIPE_PRICE_BUILDER",
    founding_builder: "STRIPE_PRICE_FOUNDING_BUILDER",
    team: "STRIPE_PRICE_TEAM",
  }[plan];
}
