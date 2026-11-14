import {
  TIER_QUOTA,
  apiBase,
  clientIp,
  detail,
  json,
  mintPlaintext,
  sha256Hex,
  siteUrl,
} from "./_lib.js";
import { isAdminEmail, publicApiAllowed } from "./_admin.js";

const COOKIE = "resileos_session";
const FAIL_LIMIT = 5;
const LOCK_MS = 15 * 60 * 1000;
const REVEAL_MS = 10 * 60 * 1000;

export function memoryKv() {
  const data = new Map();
  return {
    async get(key) {
      return data.has(key) ? data.get(key) : null;
    },
    async put(key, value) {
      data.set(key, String(value));
    },
    async delete(key) {
      data.delete(key);
    },
  };
}

export function normalizeEmail(value) {
  if (typeof value !== "string") return "";
  const email = value.trim().toLowerCase();
  if (email.length < 3 || email.length > 254) return "";
  if (/[\r\n\0]/.test(email)) return "";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return "";
  return email;
}

export function safeNext(value, fallback = "/account") {
  const next = typeof value === "string" ? value.trim() : "";
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return fallback;
  if (next.length > 200 || /[\r\n\0]/.test(next)) return fallback;
  if (next.startsWith("/api/") || next.startsWith("/login")) return fallback;
  return next;
}

export const LOGIN_MISMATCH = "That email and password don't match. Try again, or choose \u201cEmail me a link\u201d.";
export const LOGIN_LOCKED = "Too many tries. Wait 15 minutes, or choose \u201cEmail me a link\u201d.";

// Cloudflare Workers' WebCrypto rejects PBKDF2 above 100000 iterations, so a higher
// setting would make every password save and sign-in fail on the live site.
export const PBKDF2_ITERATIONS = 100000;

export function passwordIterations(env) {
  void env;
  return PBKDF2_ITERATIONS;
}

export function magicTtlMs(env) {
  const sec = Number((env && env.MAGIC_LINK_TTL_SECONDS) || 900);
  if (!Number.isFinite(sec) || sec < 60) return 15 * 60 * 1000;
  return Math.min(Math.floor(sec), 3600) * 1000;
}

export function sessionTtlMs(env) {
  const sec = Number((env && env.SESSION_TTL_SECONDS) || 1209600);
  if (!Number.isFinite(sec) || sec < 300) return 14 * 24 * 60 * 60 * 1000;
  return Math.floor(sec) * 1000;
}

function intEnv(env, name, fallback) {
  const raw = Number(env && env[name]);
  if (!Number.isFinite(raw) || raw < 1) return fallback;
  return Math.floor(raw);
}

function b64(bytes) {
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function fromB64(value) {
  const bin = atob(value);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) out[i] = bin.charCodeAt(i);
  return out;
}

export function randomToken(size = 32) {
  const buf = crypto.getRandomValues(new Uint8Array(size));
  return b64(buf).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

export function timingSafeEqual(a, b) {
  const left = a instanceof Uint8Array ? a : new Uint8Array();
  const right = b instanceof Uint8Array ? b : new Uint8Array();
  const len = Math.max(left.length, right.length);
  let out = left.length === right.length ? 0 : 1;
  for (let i = 0; i < len; i += 1) out |= (left[i] || 0) ^ (right[i] || 0);
  return out === 0;
}

export function sessionCookie(id, maxAgeSec) {
  return [
    `${COOKIE}=${id}`,
    "HttpOnly",
    "Secure",
    "SameSite=Lax",
    "Path=/",
    `Max-Age=${Math.max(0, Math.floor(maxAgeSec))}`,
  ].join("; ");
}

export function clearSessionCookie() {
  return `${COOKIE}=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0`;
}

export function readCookie(request, name) {
  const header = request.headers.get("cookie") || "";
  for (const part of header.split(";")) {
    const eq = part.indexOf("=");
    if (eq === -1) continue;
    const key = part.slice(0, eq).trim();
    if (key === name) return part.slice(eq + 1).trim();
  }
  return "";
}

export function hostAllowed(host, env) {
  const value = String(host || "").toLowerCase();
  if (value === "resileosai.fun" || value === "www.resileosai.fun") return true;
  if (value === "localhost" || value.startsWith("localhost:") || value.startsWith("127.0.0.1")) return true;
  if (value.endsWith(".pages.dev")) return true;
  const site = env && env.RESILEOS_SITE_URL;
  if (site) {
    try {
      if (new URL(site).host.toLowerCase() === value) return true;
    } catch {
      /* ignore a bad site URL */
    }
  }
  return false;
}

export function originAllowed(request, env) {
  const candidate = request.headers.get("origin") || request.headers.get("referer") || "";
  if (!candidate) return false;
  try {
    return hostAllowed(new URL(candidate).host, env);
  } catch {
    return false;
  }
}

export function csrfOk(request, record) {
  const got = request.headers.get("x-csrf-token") || "";
  const want = (record && record.csrf) || "";
  if (!got || !want || got.length !== want.length) return false;
  return timingSafeEqual(new TextEncoder().encode(got), new TextEncoder().encode(want));
}

export function emailMode(env) {
  const from = String((env && env.EMAIL_FROM) || "").trim();
  if (!from || !from.includes("@")) return "";
  if (env.EMAIL && typeof env.EMAIL.send === "function") return "cloudflare-binding";
  if (String(env.CLOUDFLARE_EMAIL_API_TOKEN || "").trim() && String(env.CLOUDFLARE_ACCOUNT_ID || "").trim()) {
    return "cloudflare-api";
  }
  if (String(env.RESEND_API_KEY || env.EMAIL_API_KEY || "").trim()) return "resend";
  return "";
}

export async function sendEmail(env, message, deps = {}) {
  const mode = emailMode(env);
  if (!mode) {
    const err = new Error("email not configured");
    err.code = "email_not_configured";
    throw err;
  }
  if (mode === "cloudflare-binding") {
    await env.EMAIL.send({
      to: message.to,
      from: String(env.EMAIL_FROM).trim(),
      subject: message.subject,
      text: message.text,
    });
    return;
  }
  const fetchImpl = deps.fetchImpl || fetch;
  if (mode === "cloudflare-api") {
    const account = String(env.CLOUDFLARE_ACCOUNT_ID).trim();
    const res = await fetchImpl(
      `https://api.cloudflare.com/client/v4/accounts/${account}/email/sending/send`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${String(env.CLOUDFLARE_EMAIL_API_TOKEN).trim()}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          to: message.to,
          from: String(env.EMAIL_FROM).trim(),
          subject: message.subject,
          text: message.text,
        }),
      }
    );
    if (!res.ok) throw new Error("email send failed");
    return;
  }
  const url = String(env.EMAIL_API_URL || "https://api.resend.com/emails").replace(/\/$/, "");
  const res = await fetchImpl(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${String(env.RESEND_API_KEY || env.EMAIL_API_KEY).trim()}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: String(env.EMAIL_FROM).trim(),
      to: [message.to],
      subject: message.subject,
      text: message.text,
    }),
  });
  if (!res.ok) throw new Error("email send failed");
}

async function bump(kv, key, limit) {
  const hits = Number((await kv.get(key)) || "0");
  if (hits >= limit) return false;
  await kv.put(key, String(hits + 1), { expirationTtl: 3600 });
  return true;
}

export async function issueMagicLink({ kv, email, purpose, ip, now, ttlMs, limits }) {
  const hour = Math.floor(now / 3600000);
  const ipOk = await bump(kv, `rl:magic:ip:${ip}:${hour}`, limits.ip);
  if (!ipOk) {
    return { ok: false, status: 429, detail: "Too many emails from this network. Wait an hour and try again." };
  }
  const emailOk = await bump(kv, `rl:magic:email:${email}:${hour}`, limits.email);
  if (!emailOk) {
    return { ok: false, status: 429, detail: "We've sent several emails to this address already. Check your inbox and spam folder, or wait an hour." };
  }
  const token = randomToken(32);
  const digest = await sha256Hex(token);
  const rec = { email, purpose: purpose || "login", exp: now + ttlMs, used: false };
  await kv.put(`magic:${digest}`, JSON.stringify(rec), {
    expirationTtl: Math.max(60, Math.ceil(ttlMs / 1000)),
  });
  return { ok: true, token, exp: rec.exp };
}

export async function consumeMagicLink({ kv, token, now }) {
  if (!token || token.length < 20) return { ok: false, reason: "invalid" };
  const digest = await sha256Hex(token);
  const raw = await kv.get(`magic:${digest}`);
  if (!raw) return { ok: false, reason: "invalid" };
  let rec;
  try {
    rec = JSON.parse(raw);
  } catch {
    return { ok: false, reason: "invalid" };
  }
  if (!rec || rec.used) return { ok: false, reason: "used" };
  if (typeof rec.exp !== "number" || rec.exp <= now) return { ok: false, reason: "expired" };
  rec.used = true;
  await kv.put(`magic:${digest}`, JSON.stringify(rec));
  return { ok: true, email: rec.email, purpose: rec.purpose || "login" };
}

function accountStorageKey(email) {
  return `account:${email}`;
}

export async function loadAccount(kv, email) {
  const raw = await kv.get(accountStorageKey(email));
  if (!raw) return null;
  try {
    const rec = JSON.parse(raw);
    return rec && typeof rec === "object" ? rec : null;
  } catch {
    return null;
  }
}

async function saveAccount(kv, account) {
  await kv.put(accountStorageKey(account.email), JSON.stringify(account));
}

async function revokeDigest(kv, digest) {
  if (!digest) return;
  const raw = await kv.get(`key:${digest}`);
  if (raw) {
    try {
      const rec = JSON.parse(raw);
      rec.revoked = true;
      await kv.put(`key:${digest}`, JSON.stringify(rec));
    } catch {
      /* a corrupt record stays unreadable to the API */
    }
  }
  await kv.delete(`seal:${digest}`);
}

export async function attachDigest(kv, account, digest) {
  const raw = await kv.get(`key:${digest}`);
  if (!raw) return account;
  let rec;
  try {
    rec = JSON.parse(raw);
  } catch {
    return account;
  }
  if (!rec || rec.revoked) return account;
  if (account.key_digest && account.key_digest !== digest) {
    await revokeDigest(kv, account.key_digest);
  }
  account.key_digest = digest;
  account.prefix = rec.prefix || "";
  account.plan = rec.plan || account.plan || "free";
  account.tier = rec.tier || account.tier || "free";
  account.quota = rec.quota ?? account.quota;
  if (rec.plan === "free") account.free_issued = true;
  await saveAccount(kv, account);
  return account;
}

export async function ensureAccount(kv, email, now) {
  let account = await loadAccount(kv, email);
  if (!account) {
    account = {
      email,
      created_at: new Date(now).toISOString(),
      key_digest: "",
      prefix: "",
      plan: "free",
      tier: TIER_QUOTA.free.tier,
      quota: TIER_QUOTA.free.quota,
      free_issued: false,
      session_generation: 0,
      password: null,
    };
  }
  const pending = await kv.get(`pending:${email}`);
  if (pending) {
    let pendingRec = null;
    try {
      pendingRec = JSON.parse((await kv.get(`key:${pending}`)) || "null");
    } catch {
      pendingRec = null;
    }
    const pendingPaid = Boolean(pendingRec && pendingRec.plan && pendingRec.plan !== "free" && !pendingRec.revoked);
    if (!account.key_digest || (pendingPaid && account.plan === "free")) {
      await attachDigest(kv, account, pending);
    }
    await kv.delete(`pending:${email}`);
  }
  await saveAccount(kv, account);
  return account;
}

export async function createSession({ kv, env, email, now, extra }) {
  const secret = String((env && env.SESSION_SECRET) || "").trim();
  if (secret.length < 16) return { ok: false, status: 503, detail: "session secret not configured" };
  const account = await ensureAccount(kv, email, now);
  const id = randomToken(32);
  const storage = await sha256Hex(`${secret}:${id}`);
  const csrf = randomToken(32);
  const ttl = sessionTtlMs(env);
  const more = extra || {};
  const rec = {
    email,
    csrf,
    exp: now + ttl,
    gen: account.session_generation || 0,
    reveal_until: more.reveal_until || 0,
    reset_until: more.reset_until || 0,
  };
  await kv.put(`session:${storage}`, JSON.stringify(rec), {
    expirationTtl: Math.max(60, Math.ceil(ttl / 1000)),
  });
  return {
    ok: true,
    id,
    csrf,
    storage,
    cookie: sessionCookie(id, Math.ceil(ttl / 1000)),
    record: rec,
  };
}

export async function readSession({ kv, env, request, now }) {
  const secret = String((env && env.SESSION_SECRET) || "").trim();
  if (secret.length < 16) return null;
  const id = readCookie(request, COOKIE);
  if (!id) return null;
  const storage = await sha256Hex(`${secret}:${id}`);
  const raw = await kv.get(`session:${storage}`);
  if (!raw) return null;
  let rec;
  try {
    rec = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!rec || typeof rec.exp !== "number" || rec.exp <= now) {
    await kv.delete(`session:${storage}`);
    return null;
  }
  const account = await loadAccount(kv, rec.email);
  if (!account || (account.session_generation || 0) !== (rec.gen || 0)) {
    await kv.delete(`session:${storage}`);
    return null;
  }
  return { id, storage, record: rec, account, email: rec.email };
}

export async function hashPassword(password, env, saltBytes) {
  const iterations = passwordIterations(env);
  const salt = saltBytes || crypto.getRandomValues(new Uint8Array(16));
  const material = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(password),
    "PBKDF2",
    false,
    ["deriveBits"]
  );
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt, iterations },
    material,
    256
  );
  return {
    salt_b64: b64(salt),
    hash_b64: b64(new Uint8Array(bits)),
    iterations,
  };
}

export async function verifyPassword(password, stored) {
  if (!stored || !stored.salt_b64 || !stored.hash_b64) return false;
  const iterations = Number(stored.iterations);
  if (!Number.isFinite(iterations) || iterations < 100000) return false;
  const salt = fromB64(stored.salt_b64);
  const expected = fromB64(stored.hash_b64);
  const material = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(password),
    "PBKDF2",
    false,
    ["deriveBits"]
  );
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt, iterations },
    material,
    256
  );
  return timingSafeEqual(new Uint8Array(bits), expected);
}

let dummyPassword = null;
async function dummyStored(env) {
  if (!dummyPassword) dummyPassword = await hashPassword("not-a-real-account-password", env);
  return dummyPassword;
}

async function readLock(kv, email) {
  const raw = await kv.get(`lock:${email}`);
  if (!raw) return { fails: 0, locked_until: 0 };
  try {
    const rec = JSON.parse(raw);
    return { fails: Number(rec.fails) || 0, locked_until: Number(rec.locked_until) || 0 };
  } catch {
    return { fails: 0, locked_until: 0 };
  }
}

export async function loginWithPassword({ kv, env, email, password, ip, now }) {
  const hour = Math.floor(now / 3600000);
  const ipOk = await bump(kv, `rl:login:ip:${ip}:${hour}`, intEnv(env, "LOGIN_IP_PER_HOUR", 30));
  if (!ipOk) return { ok: false, status: 429, detail: "Too many sign-in attempts from this network. Try again in an hour, or choose \u201cEmail me a link\u201d." };
  const lock = await readLock(kv, email);
  if (lock.locked_until && lock.locked_until > now) {
    return { ok: false, status: 429, detail: LOGIN_LOCKED };
  }
  const account = await loadAccount(kv, email);
  const stored = account && account.password ? account.password : await dummyStored(env);
  const matches = await verifyPassword(password, stored);
  if (!account || !account.password || !matches) {
    if (account && account.password) {
      const fails = lock.fails + 1;
      const lockedUntil = fails >= FAIL_LIMIT ? now + LOCK_MS : 0;
      await kv.put(`lock:${email}`, JSON.stringify({ fails, locked_until: lockedUntil }), { expirationTtl: 3600 });
      if (fails >= FAIL_LIMIT) {
        return { ok: false, status: 429, detail: LOGIN_LOCKED };
      }
    }
    return { ok: false, status: 401, detail: LOGIN_MISMATCH };
  }
  await kv.delete(`lock:${email}`);
  return createSession({ kv, env, email, now });
}

export async function setPassword({ kv, env, email, password, current, now, resetOk }) {
  if (typeof password !== "string" || password.length < 10 || password.length > 200) {
    return { ok: false, status: 400, detail: "Use a password of at least 10 characters (200 at most)." };
  }
  const account = await ensureAccount(kv, email, now);
  if (account.password && !resetOk) {
    if (!current) {
      return { ok: false, status: 400, detail: "Enter your current password to change it, or use \u201cForgot password\u201d." };
    }
    const matches = await verifyPassword(current, account.password);
    if (!matches) {
      return { ok: false, status: 401, detail: "Your current password isn't right. Try again, or use \u201cForgot password\u201d." };
    }
  }
  account.password = await hashPassword(password, env);
  await saveAccount(kv, account);
  await kv.delete(`lock:${email}`);
  return { ok: true };
}

export async function sealSecret(plaintext, secret) {
  const pepper = String(secret || "");
  if (pepper.length < 16) throw new Error("seal secret too short");
  const keyBytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(pepper));
  const key = await crypto.subtle.importKey("raw", keyBytes, "AES-GCM", false, ["encrypt"]);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = new Uint8Array(
    await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, new TextEncoder().encode(plaintext))
  );
  const packed = new Uint8Array(iv.length + ct.length);
  packed.set(iv, 0);
  packed.set(ct, iv.length);
  return b64(packed);
}

export async function openSeal(payload, secret) {
  if (!payload) throw new Error("missing seal");
  const pepper = String(secret || "");
  if (pepper.length < 16) throw new Error("seal secret too short");
  const packed = fromB64(payload);
  const iv = packed.slice(0, 12);
  const ct = packed.slice(12);
  const keyBytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(pepper));
  const key = await crypto.subtle.importKey("raw", keyBytes, "AES-GCM", false, ["decrypt"]);
  const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, ct);
  return new TextDecoder().decode(plain);
}

export async function mintStoredKey({ kv, env, plan, email, name }) {
  if (String((env && env.KEY_SEAL_SECRET) || "").trim().length < 16) {
    return { ok: false, status: 503, detail: "key seal is not configured" };
  }
  const mapped = TIER_QUOTA[plan] ? plan : "free";
  const quota = TIER_QUOTA[mapped];
  const plaintext = mintPlaintext();
  const digest = await sha256Hex(plaintext);
  const prefix = plaintext.slice(0, 12);
  const record = {
    name: String(name || mapped).slice(0, 64),
    tier: quota.tier,
    quota: quota.quota,
    plan: mapped,
    email: email || null,
    prefix,
    revoked: false,
    created_at: new Date().toISOString(),
  };
  await kv.put(`key:${digest}`, JSON.stringify(record));
  await kv.put(`seal:${digest}`, await sealSecret(plaintext, env.KEY_SEAL_SECRET));
  return { ok: true, plaintext, digest, record, prefix };
}

export async function createFreeKey({ kv, env, email, now }) {
  const account = await ensureAccount(kv, email, now);
  if (account.free_issued || account.key_digest) {
    return { ok: false, status: 409, detail: "This account already has a key. Rotate it, or upgrade." };
  }
  const minted = await mintStoredKey({ kv, env, plan: "free", email, name: "free" });
  if (!minted.ok) return minted;
  account.free_issued = true;
  await attachDigest(kv, account, minted.digest);
  const saved = JSON.parse((await kv.get(`key:${minted.digest}`)) || "{}");
  if (saved.api_key || saved.plaintext) {
    return { ok: false, status: 500, detail: "Key record was not stored safely." };
  }
  return {
    ok: true,
    prefix: minted.prefix,
    plan: "free",
    tier: minted.record.tier,
    quota: minted.record.quota,
  };
}

export async function rotateKey({ kv, env, email, now }) {
  const account = await loadAccount(kv, email);
  if (!account || !account.key_digest) {
    return { ok: false, status: 409, detail: "This account has no key to rotate." };
  }
  const old = account.key_digest;
  const plan = TIER_QUOTA[account.plan] ? account.plan : "free";
  const minted = await mintStoredKey({ kv, env, plan, email, name: plan });
  if (!minted.ok) return minted;
  await revokeDigest(kv, old);
  account.key_digest = minted.digest;
  account.prefix = minted.prefix;
  account.tier = minted.record.tier;
  account.quota = minted.record.quota;
  account.plan = minted.record.plan;
  account.session_generation = (account.session_generation || 0) + 1;
  await saveAccount(kv, account);
  return { ok: true, prefix: minted.prefix, plan: account.plan, digest: minted.digest, old };
}

export async function revealKey({ kv, env, session, now }) {
  if (!session.record.reveal_until || session.record.reveal_until < now) {
    return { ok: false, status: 403, detail: "Confirm by email before revealing a key." };
  }
  if (!session.account.key_digest) return { ok: false, status: 409, detail: "This account has no key." };
  let plaintext = "";
  try {
    plaintext = await openSeal(await kv.get(`seal:${session.account.key_digest}`), env.KEY_SEAL_SECRET);
  } catch {
    return { ok: false, status: 503, detail: "Key is unavailable." };
  }
  session.record.reveal_until = 0;
  await kv.put(`session:${session.storage}`, JSON.stringify(session.record));
  return { ok: true, api_key: plaintext, prefix: session.account.prefix || plaintext.slice(0, 12) };
}

export async function hmacHex(secret, message) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(message));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function trialHeaders(secret, ip, ts) {
  const proof = await hmacHex(secret, `${ip}\n${ts}`);
  return {
    "X-Resileos-Trial": "1",
    "X-Resileos-Client-Ip": ip,
    "X-Resileos-Trial-Ts": String(ts),
    "X-Resileos-Trial-Proof": proof,
  };
}

function momentOf(now) {
  return typeof now === "function" ? now() : Date.now();
}

async function readJson(request) {
  try {
    return await request.json();
  } catch {
    return {};
  }
}

function noStore(response) {
  response.headers.set("Cache-Control", "no-store");
  return response;
}

export async function handleMagicLink({ request, env, now, send }) {
  if (!originAllowed(request, env)) return detail("Cross-site request blocked.", 403);
  if (!emailMode(env)) return detail("email not configured", 503);
  const kv = env.KEYS;
  if (!kv) return detail("Key storage is not bound.", 503);
  const body = await readJson(request);
  let purpose = body.purpose === "reset" || body.purpose === "reveal" ? body.purpose : "login";
  const clock = momentOf(now);
  const session = await readSession({ kv, env, request, now: clock });
  let email = normalizeEmail(body.email);
  if ((purpose === "reset" || purpose === "reveal") && session) email = session.email;
  if (!email) return detail("Enter a full email address, like you@example.com.", 400);
  if (!session && purpose === "reveal") return detail("Sign in first.", 401);
  const issued = await issueMagicLink({
    kv,
    email,
    purpose,
    ip: clientIp(request),
    now: clock,
    ttlMs: magicTtlMs(env),
    limits: {
      ip: intEnv(env, "MAGIC_LINK_IP_PER_HOUR", 8),
      email: intEnv(env, "MAGIC_LINK_EMAIL_PER_HOUR", 5),
    },
  });
  if (!issued.ok) return detail(issued.detail, issued.status);
  let url = `${siteUrl(env).replace(/\/$/, "")}/api/session/verify?token=${encodeURIComponent(issued.token)}`;
  const requestedNext = safeNext(body.next, "");
  if (purpose === "login" && requestedNext) url += `&next=${encodeURIComponent(requestedNext)}`;
  const minutes = Math.round(magicTtlMs(env) / 60000);
  const subject = {
    login: "Your Resileos sign-in link",
    reset: "Reset your Resileos password",
    reveal: "Confirm key reveal for Resileos",
  }[purpose];
  const text = [
    subject,
    "",
    url,
    "",
    `This link expires in ${minutes} minutes and works once.`,
    "If you did not ask for it, ignore this email.",
  ].join("\n");
  const deliver = send || ((message) => sendEmail(env, message));
  try {
    await deliver({ to: email, subject, text });
  } catch (err) {
    await kv.delete(`magic:${await sha256Hex(issued.token)}`);
    if (err && err.code === "email_not_configured") return detail("email not configured", 503);
    return detail("We couldn't send the email just now. Try again in a minute.", 502);
  }
  return noStore(json({ ok: true }));
}

export async function handleVerify({ request, env, now }) {
  const kv = env.KEYS;
  if (!kv) return detail("Key storage is not bound.", 503);
  const clock = momentOf(now);
  const url = new URL(request.url);
  const consumed = await consumeMagicLink({ kv, token: url.searchParams.get("token") || "", now: clock });
  if (!consumed.ok) {
    return new Response(null, {
      status: 302,
      headers: { Location: "/login?error=link", "Cache-Control": "no-store" },
    });
  }
  const extra = {};
  let next = "/account";
  if (consumed.purpose === "reveal") {
    extra.reveal_until = clock + REVEAL_MS;
    next = "/account?reveal=ready";
  } else if (consumed.purpose === "reset") {
    extra.reset_until = clock + magicTtlMs(env);
    next = "/login?step=reset";
  } else {
    next = safeNext(url.searchParams.get("next"), "/account");
  }
  const session = await createSession({ kv, env, email: consumed.email, now: clock, extra });
  if (!session.ok) return detail(session.detail, session.status);
  if (consumed.purpose === "login") {
    const account = await loadAccount(kv, consumed.email);
    if (account && !account.password) {
      next = `/login?step=set-password&next=${encodeURIComponent(next)}`;
    }
  }
  return new Response(null, {
    status: 302,
    headers: {
      Location: next,
      "Set-Cookie": session.cookie,
      "Cache-Control": "no-store",
    },
  });
}

export function loginFields(body) {
  const source = body && typeof body === "object" ? body : {};
  const pick = (value) => (typeof value === "string" ? value : "");
  // Older forms and password managers may post the address as "username".
  const raw = pick(source.email).trim() ? pick(source.email) : pick(source.username);
  return { raw: raw.trim(), email: normalizeEmail(raw), password: pick(source.password) };
}

export async function handleLogin({ request, env, now }) {
  if (!originAllowed(request, env)) return detail("Cross-site request blocked.", 403);
  const kv = env.KEYS;
  if (!kv) return detail("Key storage is not bound.", 503);
  const body = await readJson(request);
  const { raw, email, password } = loginFields(body);
  if (!raw) return detail("Enter your email address.", 400);
  if (!email) {
    return detail("Enter the full email address for your account, like you@example.com. Usernames aren't used to sign in.", 400);
  }
  if (!password) return detail("Enter your password, or choose \u201cEmail me a link\u201d.", 400);
  const result = await loginWithPassword({
    kv,
    env,
    email,
    password,
    ip: clientIp(request),
    now: momentOf(now),
  });
  if (!result.ok) return detail(result.detail, result.status);
  return noStore(json({ ok: true, csrf: result.csrf, email }, 200, { "Set-Cookie": result.cookie }));
}

export async function handleLogout({ request, env, now }) {
  if (!originAllowed(request, env)) return detail("Cross-site request blocked.", 403);
  const kv = env.KEYS;
  if (!kv) return detail("Key storage is not bound.", 503);
  const session = await readSession({ kv, env, request, now: momentOf(now) });
  if (session && !csrfOk(request, session.record)) return detail("This page is out of date. Refresh it and try again.", 403);
  if (session) await kv.delete(`session:${session.storage}`);
  return noStore(json({ ok: true }, 200, { "Set-Cookie": clearSessionCookie() }));
}

export function publicAccount(session, now) {
  const account = session.account;
  return {
    signed_in: true,
    email: session.email,
    plan: account.plan || "free",
    tier: account.tier || "free",
    quota: account.quota ?? TIER_QUOTA.free.quota,
    prefix: account.prefix || "",
    has_key: Boolean(account.key_digest),
    has_password: Boolean(account.password),
    free_issued: Boolean(account.free_issued),
    csrf: session.record.csrf,
    reveal_ready: (session.record.reveal_until || 0) > now,
    reset_ready: (session.record.reset_until || 0) > now,
  };
}

export async function handleMe({ request, env, now, fetchImpl }) {
  const kv = env.KEYS;
  if (!kv) return detail("Key storage is not bound.", 503);
  const clock = momentOf(now);
  const session = await readSession({ kv, env, request, now: clock });
  if (!session) return noStore(json({ signed_in: false }));
  const body = publicAccount(session, clock);
  body.admin = isAdminEmail(session.email, env);
  if (session.account.key_digest && String(env.KEY_SEAL_SECRET || "").length >= 16) {
    try {
      const apiKey = await openSeal(await kv.get(`seal:${session.account.key_digest}`), env.KEY_SEAL_SECRET);
      const fetchFn = fetchImpl || fetch;
      const res = await fetchFn(`${apiBase(env).replace(/\/$/, "")}/usage`, {
        headers: { "X-API-Key": apiKey, accept: "application/json" },
      });
      if (res.ok) {
        const usage = await res.json();
        body.count = usage.count;
        if (typeof usage.quota === "number") body.quota = usage.quota;
        body.usage = {
          count: usage.count,
          quota: usage.quota,
          month: usage.month,
          tier: usage.tier,
          plan: usage.plan,
          unlimited: usage.unlimited,
        };
      }
    } catch {
      /* the account page still renders without a live count */
    }
  }
  return noStore(json(body));
}

async function requireUser({ request, env, now }) {
  if (!originAllowed(request, env)) return { response: detail("Cross-site request blocked.", 403) };
  const kv = env.KEYS;
  if (!kv) return { response: detail("Key storage is not bound.", 503) };
  const clock = momentOf(now);
  const session = await readSession({ kv, env, request, now: clock });
  if (!session) return { response: detail("You're signed out. Sign in again to continue.", 401) };
  if (!csrfOk(request, session.record)) {
    return { response: detail("This page is out of date. Refresh it and try again.", 403) };
  }
  return { kv, session, now: clock };
}

export async function handlePassword({ request, env, now }) {
  const gate = await requireUser({ request, env, now });
  if (gate.response) return gate.response;
  const body = await readJson(request);
  const resetOk = (gate.session.record.reset_until || 0) > gate.now;
  const result = await setPassword({
    kv: gate.kv,
    env,
    email: gate.session.email,
    password: body.password,
    current: body.current_password,
    now: gate.now,
    resetOk,
  });
  if (!result.ok) return detail(result.detail, result.status);
  if (resetOk) {
    gate.session.record.reset_until = 0;
    await gate.kv.put(`session:${gate.session.storage}`, JSON.stringify(gate.session.record));
  }
  return noStore(json({ ok: true }));
}

export async function handleFreeKey({ request, env, now }) {
  const gate = await requireUser({ request, env, now });
  if (gate.response) return gate.response;
  const result = await createFreeKey({ kv: gate.kv, env, email: gate.session.email, now: gate.now });
  if (!result.ok) return detail(result.detail, result.status);
  return noStore(json({
    ok: true,
    prefix: result.prefix,
    plan: result.plan,
    tier: result.tier,
    quota: result.quota,
  }));
}

export async function handleRotate({ request, env, now }) {
  const gate = await requireUser({ request, env, now });
  if (gate.response) return gate.response;
  const result = await rotateKey({ kv: gate.kv, env, email: gate.session.email, now: gate.now });
  if (!result.ok) return detail(result.detail, result.status);
  return noStore(json(
    { ok: true, prefix: result.prefix, plan: result.plan },
    200,
    { "Set-Cookie": clearSessionCookie() }
  ));
}

export async function handleReveal({ request, env, now }) {
  const gate = await requireUser({ request, env, now });
  if (gate.response) return gate.response;
  const result = await revealKey({ kv: gate.kv, env, session: gate.session, now: gate.now });
  if (!result.ok) return detail(result.detail, result.status);
  return noStore(json({ api_key: result.api_key, prefix: result.prefix }));
}

export async function handleProxy({ request, env, params, fetchImpl, now }) {
  const method = request.method.toUpperCase();
  if (method === "OPTIONS") return new Response(null, { status: 204 });
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method) && !originAllowed(request, env)) {
    return detail("Cross-site request blocked.", 403);
  }
  const kv = env.KEYS;
  if (!kv) return detail("Key storage is not bound.", 503);
  const parts = Array.isArray(params && params.path) ? params.path : [];
  if (!parts.length || parts.some((part) => !part || part === "." || part === ".." || String(part).includes("\\") || String(part).includes(":"))) {
    return detail("Unknown API path.", 404);
  }
  const clock = momentOf(now);
  const session = await readSession({ kv, env, request, now: clock });
  if (method !== "OPTIONS" && !publicApiAllowed(method, parts)) {
    if (!session) return detail("This tool is for site admins. Sign in with an admin account.", 401);
    if (!isAdminEmail(session.email, env)) return detail("This tool is for site admins only.", 403);
  }
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  headers.set("accept", request.headers.get("accept") || "application/json");
  if (session) {
    if (["POST", "PUT", "PATCH", "DELETE"].includes(method) && !csrfOk(request, session.record)) {
      return detail("This page is out of date. Refresh it and try again.", 403);
    }
    if (!session.account.key_digest && !session.account.free_issued) {
      // First chat after sign-in: give the account its one free key on the server,
      // under the same per-network limit as /api/free-key.
      const rateKey = `rate:${clientIp(request)}`;
      const hits = Number((await kv.get(rateKey)) || "0");
      if (hits < intEnv(env, "FREE_KEY_RATE_PER_HOUR", 5)) {
        const created = await createFreeKey({ kv, env, email: session.email, now: clock });
        if (created.ok) {
          await kv.put(rateKey, String(hits + 1), { expirationTtl: 3600 });
          session.account = (await loadAccount(kv, session.email)) || session.account;
        }
      }
    }
    if (!session.account.key_digest) {
      return detail("This account has no active key. Open Account to set one up.", 409);
    }
    let apiKey = "";
    try {
      apiKey = await openSeal(await kv.get(`seal:${session.account.key_digest}`), env.KEY_SEAL_SECRET);
    } catch {
      return detail("Key is unavailable.", 503);
    }
    headers.set("X-API-Key", apiKey);
  } else {
    const secret = String(env.RESILEOS_PROXY_SECRET || "").trim();
    if (secret.length < 16) return detail("Sign in to continue.", 401);
    const stamped = await trialHeaders(secret, clientIp(request), Math.floor(clock / 1000));
    for (const [name, value] of Object.entries(stamped)) headers.set(name, value);
  }
  const url = new URL(request.url);
  const target = `${apiBase(env).replace(/\/$/, "")}/${parts.map((part) => encodeURIComponent(part)).join("/")}${url.search}`;
  const fetchFn = fetchImpl || fetch;
  const init = { method, headers };
  if (method !== "GET" && method !== "HEAD") init.body = request.body;
  const upstream = await fetchFn(target, init);
  const out = new Headers();
  for (const name of ["content-type", "x-usage-count", "x-usage-quota", "x-ratelimit-remaining", "x-trial-remaining", "retry-after"]) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export async function sessionEmail(request, env, now) {
  const kv = env && env.KEYS;
  if (!kv) return "";
  const session = await readSession({ kv, env, request, now: momentOf(now) });
  return session ? session.email : "";
}
