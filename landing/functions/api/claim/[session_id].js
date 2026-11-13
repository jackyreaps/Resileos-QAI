import { TIER_QUOTA, apiBase, detail, json } from "../../_lib.js";
import { attachDigest, ensureAccount, mintStoredKey, originAllowed, readSession } from "../../_auth.js";

export async function onRequestGet({ request, params, env }) {
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
      "Key not ready yet (webhook pending) or already claimed. Refresh in a few seconds, or sign in with the checkout email.",
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

  const signedIn = await readSession({ kv, env, request, now: Date.now() });
  if (signedIn && !originAllowed(request, env)) {
    return detail("Cross-site request blocked.", 403);
  }

  const plan = (session.metadata && session.metadata.plan) || "builder";
  const mapped = TIER_QUOTA[plan] ? plan : "builder";
  const email =
    (session.metadata && session.metadata.account_email) ||
    (session.customer_details && session.customer_details.email) ||
    session.customer_email ||
    null;
  const minted = await mintStoredKey({
    kv,
    env,
    plan: mapped,
    email,
    name: `stripe:${mapped}`,
  });
  if (!minted.ok) return detail(minted.detail, minted.status);
  if (email) await kv.put(`pending:${String(email).trim().toLowerCase()}`, minted.digest);

  let attached = false;
  if (signedIn) {
    const account = await ensureAccount(kv, signedIn.email, Date.now());
    await attachDigest(kv, account, minted.digest);
    if (email) await kv.delete(`pending:${String(email).trim().toLowerCase()}`);
    attached = true;
  }

  const payload = {
    tier: minted.record.tier,
    quota: minted.record.quota,
    plan: minted.record.plan,
    prefix: minted.prefix,
    email,
    attached,
    base_url: apiBase(env),
    header: "X-API-Key",
  };
  const reveal = new URL(request.url).searchParams.get("delivery") === "key";
  if (reveal && !attached) payload.api_key = minted.plaintext;
  await kv.put(`claim:${sessionId}`, "taken");
  return json(payload);
}
