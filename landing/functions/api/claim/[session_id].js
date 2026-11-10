import {
  TIER_QUOTA,
  apiBase,
  detail,
  json,
  mintPlaintext,
  sha256Hex,
} from "../../_lib.js";

export async function onRequestGet({ params, env }) {
  const sessionId = params.session_id;
  if (!sessionId || !/^(cs_test_|cs_live_)[A-Za-z0-9]+$/.test(sessionId)) {
    return detail("Invalid session.", 400);
  }
  if (!env.STRIPE_SECRET_KEY) return detail("Stripe is not configured.", 503);
  const kv = env.KEYS;
  if (!kv) return detail("Key storage is not bound.", 503);

  const claimed = await kv.get(`claim:${sessionId}`);
  if (claimed === "taken") {
    return detail(
      "Key not ready yet (webhook pending) or already claimed. Refresh in a few seconds, or check your email once mailer is wired.",
      404
    );
  }
  if (claimed) {
    await kv.put(`claim:${sessionId}`, "taken");
    return json(JSON.parse(claimed));
  }

  const res = await fetch(`https://api.stripe.com/v1/checkout/sessions/${sessionId}`, {
    headers: { Authorization: `Bearer ${env.STRIPE_SECRET_KEY}` },
  });
  const session = await res.json();
  if (!res.ok) return detail("Key not ready yet (webhook pending) or already claimed.", 404);
  if (session.payment_status !== "paid" && session.status !== "complete") {
    return detail("Key not ready yet (webhook pending) or already claimed.", 404);
  }

  const plan = (session.metadata && session.metadata.plan) || "builder";
  const mapped = TIER_QUOTA[plan] ? plan : "builder";
  const quota = TIER_QUOTA[mapped];
  const plaintext = mintPlaintext();
  const digest = await sha256Hex(plaintext);
  const record = {
    name: `stripe:${mapped}`,
    tier: quota.tier,
    quota: quota.quota,
    plan: mapped,
    email: (session.customer_details && session.customer_details.email) || session.customer_email || null,
    stripe_customer_id: session.customer || null,
    created_at: new Date().toISOString(),
  };
  await kv.put(`key:${digest}`, JSON.stringify(record));
  const payload = {
    api_key: plaintext,
    tier: record.tier,
    quota: record.quota,
    plan: record.plan,
    base_url: apiBase(env),
    header: "X-API-Key",
  };
  await kv.put(`claim:${sessionId}`, JSON.stringify(payload));
  await kv.put(`claim:${sessionId}`, "taken");
  return json(payload);
}
