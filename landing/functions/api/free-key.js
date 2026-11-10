import {
  TIER_QUOTA,
  apiBase,
  clientIp,
  detail,
  json,
  mintPlaintext,
  sha256Hex,
} from "../_lib.js";

export async function onRequestPost({ request, env }) {
  let body = {};
  try {
    body = await request.json();
  } catch {
    body = {};
  }
  const email = typeof body.email === "string" && body.email.includes("@") ? body.email.trim() : null;
  const name = String(body.name || "free").slice(0, 64);
  const kv = env.KEYS;
  if (!kv) return detail("Key storage is not bound.", 503);

  const ip = clientIp(request);
  const rateKey = `rate:${ip}`;
  const hits = Number((await kv.get(rateKey)) || "0");
  const limit = Number(env.FREE_KEY_RATE_PER_HOUR || "5");
  if (hits >= limit) {
    return detail("Too many free keys from this network. Try again later.", 429);
  }
  await kv.put(rateKey, String(hits + 1), { expirationTtl: 3600 });

  if (email) {
    const emailCount = Number((await kv.get(`email:${email.toLowerCase()}`)) || "0");
    if (emailCount >= 2) {
      return detail("This email already has free keys. Upgrade or contact support.", 429);
    }
  }

  const plaintext = mintPlaintext();
  const digest = await sha256Hex(plaintext);
  const quota = TIER_QUOTA.free;
  const record = {
    name,
    tier: quota.tier,
    quota: quota.quota,
    plan: "free",
    email,
    stripe_customer_id: null,
    created_at: new Date().toISOString(),
  };
  await kv.put(`key:${digest}`, JSON.stringify(record));
  if (email) {
    const emailCount = Number((await kv.get(`email:${email.toLowerCase()}`)) || "0");
    await kv.put(`email:${email.toLowerCase()}`, String(emailCount + 1));
  }

  const base = apiBase(env);
  return json({
    api_key: plaintext,
    tier: record.tier,
    quota: record.quota,
    plan: record.plan,
    base_url: base,
    header: "X-API-Key",
    note: "Store this key now — it is shown once. Send it as the X-API-Key header on every request. Optional mouth (LLM render) is off by default.",
    demo_namespace: "coming_soon",
    quickstart: {
      learn: `curl -sS -X POST ${base}/learn -H 'Content-Type: application/json' -H 'X-API-Key: ${plaintext}' -d '{"subject":"alice","relation":"parent_of","obj":"bob"}'`,
      query: `curl -sS -X POST ${base}/query -H 'Content-Type: application/json' -H 'X-API-Key: ${plaintext}' -d '{"subject":"alice","relation":"parent_of"}'`,
      chain: `curl -sS -X POST ${base}/chain -H 'Content-Type: application/json' -H 'X-API-Key: ${plaintext}' -d '{"start":"alice","relations":["parent_of","parent_of"]}'`,
    },
  });
}
