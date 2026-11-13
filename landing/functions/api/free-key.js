import { clientIp, detail, json } from "../_lib.js";
import { createFreeKey, csrfOk, originAllowed, readSession } from "../_auth.js";

export async function onRequestPost({ request, env }) {
  if (!originAllowed(request, env)) return detail("Cross-site request blocked.", 403);
  const kv = env.KEYS;
  if (!kv) return detail("Key storage is not bound.", 503);
  const session = await readSession({ kv, env, request, now: Date.now() });
  if (!session) return detail("Sign in to create a free key.", 401);
  if (!csrfOk(request, session.record)) return detail("CSRF check failed.", 403);

  const ip = clientIp(request);
  const rateKey = `rate:${ip}`;
  const hits = Number((await kv.get(rateKey)) || "0");
  const limit = Number(env.FREE_KEY_RATE_PER_HOUR || "5");
  if (hits >= limit) return detail("Too many free keys from this network. Try again later.", 429);

  const created = await createFreeKey({ kv, env, email: session.email, now: Date.now() });
  if (!created.ok) return detail(created.detail, created.status);
  await kv.put(rateKey, String(hits + 1), { expirationTtl: 3600 });
  return json({
    prefix: created.prefix,
    tier: created.tier,
    quota: created.quota,
    plan: created.plan,
    header: "X-API-Key",
    note: "The key stays on the account. Chat uses it automatically. Reveal it once from Account after an email confirmation if a server needs it directly.",
  });
}
