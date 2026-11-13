import assert from "node:assert/strict";
import { test } from "node:test";

import { sha256Hex } from "./_lib.js";
import {
  clearSessionCookie,
  consumeMagicLink,
  createFreeKey,
  createSession,
  emailMode,
  handleFreeKey,
  handleLogin,
  handleLogout,
  handleMagicLink,
  handleMe,
  handleProxy,
  handleReveal,
  handleRotate,
  handleVerify,
  hashPassword,
  issueMagicLink,
  loadAccount,
  loginWithPassword,
  memoryKv,
  readSession,
  rotateKey,
  sessionCookie,
  setPassword,
  timingSafeEqual,
  verifyPassword,
} from "./_auth.js";

const NOW = 1_700_000_000_000;

function baseEnv(kv, extra = {}) {
  return {
    KEYS: kv,
    EMAIL_FROM: "login@resileosai.fun",
    RESEND_API_KEY: "test-only",
    RESILEOS_SITE_URL: "https://resileosai.fun",
    RESILEOS_API_BASE_URL: "https://api.resileosai.fun/api/v1",
    SESSION_SECRET: "session-secret-value",
    KEY_SEAL_SECRET: "seal-secret-value-ok",
    RESILEOS_PROXY_SECRET: "proxy-secret-value",
    PASSWORD_PBKDF2_ITERATIONS: "100000",
    ...extra,
  };
}

function request(path, { method = "GET", body, headers = {}, cookie = "" } = {}) {
  const init = {
    method,
    headers: {
      origin: "https://resileosai.fun",
      ...headers,
    },
  };
  if (cookie) init.headers.cookie = cookie;
  if (body !== undefined) {
    init.headers["content-type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  return new Request("https://resileosai.fun" + path, init);
}

function tokenFrom(message) {
  const match = message.text.match(/https:\/\/\S+/);
  assert.ok(match, "email contained no link");
  return new URL(match[0]).searchParams.get("token");
}

test("session cookie is HttpOnly, Secure, and SameSite=Lax", () => {
  const cookie = sessionCookie("session-id", 60);
  assert.match(cookie, /^resileos_session=/);
  assert.match(cookie, /HttpOnly/);
  assert.match(cookie, /Secure/);
  assert.match(cookie, /SameSite=Lax/);
  assert.match(clearSessionCookie(), /Max-Age=0/);
});

test("magic link is single use and expires", async () => {
  const kv = memoryKv();
  const limits = { ip: 10, email: 10 };
  const issued = await issueMagicLink({
    kv,
    email: "ada@example.com",
    purpose: "login",
    ip: "203.0.113.8",
    now: NOW,
    ttlMs: 1000,
    limits,
  });
  assert.equal(issued.ok, true);
  const first = await consumeMagicLink({ kv, token: issued.token, now: NOW + 500 });
  assert.equal(first.ok, true);
  assert.equal(first.email, "ada@example.com");
  const second = await consumeMagicLink({ kv, token: issued.token, now: NOW + 600 });
  assert.equal(second.ok, false);
  assert.equal(second.reason, "used");

  const later = await issueMagicLink({
    kv,
    email: "bea@example.com",
    purpose: "login",
    ip: "203.0.113.9",
    now: NOW,
    ttlMs: 1000,
    limits,
  });
  const expired = await consumeMagicLink({ kv, token: later.token, now: NOW + 1001 });
  assert.equal(expired.ok, false);
  assert.equal(expired.reason, "expired");
});

test("magic link is rate limited per IP and per email", async () => {
  const kv = memoryKv();
  const emailLimits = { ip: 10, email: 1 };
  const first = await issueMagicLink({
    kv, email: "a@example.com", purpose: "login", ip: "198.51.100.2", now: NOW, ttlMs: 1000, limits: emailLimits,
  });
  const secondEmail = await issueMagicLink({
    kv, email: "a@example.com", purpose: "login", ip: "198.51.100.3", now: NOW, ttlMs: 1000, limits: emailLimits,
  });
  assert.equal(first.ok, true);
  assert.equal(secondEmail.ok, false);
  assert.equal(secondEmail.status, 429);

  const ipLimits = { ip: 1, email: 10 };
  const ipFirst = await issueMagicLink({
    kv, email: "c@example.com", purpose: "login", ip: "198.51.100.8", now: NOW, ttlMs: 1000, limits: ipLimits,
  });
  const ipSecond = await issueMagicLink({
    kv, email: "d@example.com", purpose: "login", ip: "198.51.100.8", now: NOW, ttlMs: 1000, limits: ipLimits,
  });
  assert.equal(ipFirst.ok, true);
  assert.equal(ipSecond.ok, false);
  assert.equal(ipSecond.status, 429);
});

test("email is not configured returns 503 and does not send", async () => {
  const kv = memoryKv();
  const sent = [];
  const env = { KEYS: kv, RESILEOS_SITE_URL: "https://resileosai.fun", SESSION_SECRET: "session-secret-value" };
  assert.equal(emailMode(env), "");
  const res = await handleMagicLink({
    request: request("/api/session/magic-link", { method: "POST", body: { email: "ada@example.com" } }),
    env,
    now: () => NOW,
    send: async (message) => sent.push(message),
  });
  assert.equal(res.status, 503);
  assert.deepEqual(await res.json(), { detail: "email not configured" });
  assert.equal(sent.length, 0);
});

test("verify sets the session cookie and the link cannot be reused", async () => {
  const kv = memoryKv();
  const sent = [];
  const env = baseEnv(kv);
  const sentRes = await handleMagicLink({
    request: request("/api/session/magic-link", { method: "POST", body: { email: "ada@example.com" } }),
    env,
    now: () => NOW,
    send: async (message) => sent.push(message),
  });
  assert.equal(sentRes.status, 200);
  assert.deepEqual(await sentRes.json(), { ok: true });
  assert.equal(sent[0].text.includes("rsk_"), false);
  const token = tokenFrom(sent[0]);
  const verified = await handleVerify({
    request: new Request(`https://resileosai.fun/api/session/verify?token=${encodeURIComponent(token)}`),
    env,
    now: () => NOW,
  });
  assert.equal(verified.status, 302);
  assert.equal(verified.headers.get("location"), "/account");
  const cookie = verified.headers.get("set-cookie");
  assert.match(cookie, /HttpOnly/);
  assert.match(cookie, /Secure/);
  assert.match(cookie, /SameSite=Lax/);
  const again = await handleVerify({
    request: new Request(`https://resileosai.fun/api/session/verify?token=${encodeURIComponent(token)}`),
    env,
    now: () => NOW + 1,
  });
  assert.equal(again.status, 400);
  const me = await handleMe({
    request: new Request("https://resileosai.fun/api/session/me", { headers: { cookie } }),
    env,
    now: () => NOW + 1,
    fetchImpl: async () => new Response("{}", { status: 404 }),
  });
  const body = await me.json();
  assert.equal(body.signed_in, true);
  assert.equal(body.email, "ada@example.com");
  assert.equal(body.api_key, undefined);
});

test("password hash verifies, rejects, and locks out", async () => {
  const kv = memoryKv();
  const env = baseEnv(kv);
  const email = "ada@example.com";
  const saved = await setPassword({
    kv, env, email, password: "correct horse", current: "", now: NOW, resetOk: true,
  });
  assert.equal(saved.ok, true);
  const account = await loadAccount(kv, email);
  assert.equal(await verifyPassword("correct horse", account.password), true);
  assert.equal(await verifyPassword("wrong horse!!", account.password), false);
  assert.equal(account.password.iterations >= 100000, true);
  assert.equal(timingSafeEqual(new Uint8Array([1, 2]), new Uint8Array([1, 3])), false);

  for (let i = 0; i < 4; i += 1) {
    const failed = await loginWithPassword({
      kv, env, email, password: "wrong horse!!", ip: "203.0.113.20", now: NOW,
    });
    assert.equal(failed.status, 401);
  }
  const locked = await loginWithPassword({
    kv, env, email, password: "wrong horse!!", ip: "203.0.113.20", now: NOW,
  });
  assert.equal(locked.status, 429);
  const during = await loginWithPassword({
    kv, env, email, password: "correct horse", ip: "203.0.113.21", now: NOW,
  });
  assert.equal(during.status, 429);
});

test("rotation revokes the old digest and existing sessions", async () => {
  const kv = memoryKv();
  const env = baseEnv(kv);
  const email = "ada@example.com";
  const created = await createFreeKey({ kv, env, email, now: NOW });
  assert.equal(created.ok, true);
  assert.equal(created.api_key, undefined);
  const before = await loadAccount(kv, email);
  const old = before.key_digest;
  const stored = JSON.parse(await kv.get(`key:${old}`));
  assert.equal(stored.revoked, false);
  assert.equal(Object.hasOwn(stored, "api_key"), false);
  const session = await createSession({ kv, env, email, now: NOW });
  const cookie = `resileos_session=${session.id}`;
  const rotated = await rotateKey({ kv, env, email, now: NOW + 10 });
  assert.equal(rotated.ok, true);
  assert.notEqual(rotated.digest, old);
  const revoked = JSON.parse(await kv.get(`key:${old}`));
  assert.equal(revoked.revoked, true);
  assert.equal(await kv.get(`seal:${old}`), null);
  const current = await loadAccount(kv, email);
  assert.equal(current.key_digest, rotated.digest);
  assert.equal(current.session_generation, 1);
  const dead = await readSession({
    kv,
    env,
    request: new Request("https://resileosai.fun/account", { headers: { cookie } }),
    now: NOW + 11,
  });
  assert.equal(dead, null);

  const fresh = await createSession({ kv, env, email, now: NOW + 12 });
  fresh.record.reveal_until = NOW + 100000;
  await kv.put(`session:${fresh.storage}`, JSON.stringify(fresh.record));
  const authed = await readSession({
    kv,
    env,
    request: new Request("https://resileosai.fun/account", { headers: { cookie: `resileos_session=${fresh.id}` } }),
    now: NOW + 13,
  });
  const revealed = await handleReveal({
    request: request("/api/session/reveal", {
      method: "POST",
      cookie: `resileos_session=${fresh.id}`,
      headers: { "x-csrf-token": authed.record.csrf },
    }),
    env,
    now: () => NOW + 13,
  });
  assert.equal(revealed.status, 200);
  const revealedBody = await revealed.json();
  assert.equal(await sha256Hex(revealedBody.api_key), rotated.digest);
  const hidden = await handleMe({
    request: new Request("https://resileosai.fun/api/session/me", {
      headers: { cookie: `resileos_session=${fresh.id}` },
    }),
    env,
    now: () => NOW + 14,
    fetchImpl: async () => new Response(JSON.stringify({ count: 0, quota: 5000 }), {
      status: 200,
      headers: { "content-type": "application/json" },
    }),
  });
  const hiddenBody = await hidden.json();
  assert.equal(hiddenBody.api_key, undefined);
  assert.equal(hiddenBody.prefix, current.prefix);
});

test("anonymous proxy uses the trial proof and a signed-in proxy uses the sealed key", async () => {
  const kv = memoryKv();
  const env = baseEnv(kv);
  let seen = null;
  const fetchImpl = async (url, init) => {
    const headers = new Headers(init.headers);
    seen = {
      url,
      key: headers.get("x-api-key"),
      trial: headers.get("x-resileos-trial"),
      proof: headers.get("x-resileos-trial-proof"),
    };
    return new Response("{}", { status: 200, headers: { "content-type": "application/json" } });
  };
  const anon = await handleProxy({
    request: request("/api/session/v1/chat", { method: "POST", body: { message: "hi" } }),
    env,
    params: { path: ["chat"] },
    fetchImpl,
    now: () => NOW,
  });
  assert.equal(anon.status, 200);
  assert.equal(seen.key, null);
  assert.equal(seen.trial, "1");
  assert.match(seen.proof, /^[0-9a-f]{64}$/);
  assert.equal(seen.url, "https://api.resileosai.fun/api/v1/chat");

  const blocked = await handleProxy({
    request: request("/api/session/v1/chat", {
      method: "POST",
      body: { message: "hi" },
      headers: { origin: "https://evil.example" },
    }),
    env,
    params: { path: ["chat"] },
    fetchImpl: async () => {
      throw new Error("upstream should not be called");
    },
    now: () => NOW,
  });
  assert.equal(blocked.status, 403);

  await createFreeKey({ kv, env, email: "ada@example.com", now: NOW });
  const session = await createSession({ kv, env, email: "ada@example.com", now: NOW });
  const account = await loadAccount(kv, "ada@example.com");
  const signed = await handleProxy({
    request: request("/api/session/v1/chat", {
      method: "POST",
      body: { message: "hi" },
      cookie: `resileos_session=${session.id}`,
      headers: { "x-csrf-token": session.csrf },
    }),
    env,
    params: { path: ["chat"] },
    fetchImpl,
    now: () => NOW,
  });
  assert.equal(signed.status, 200);
  assert.equal(seen.trial, null);
  assert.equal(await sha256Hex(seen.key), account.key_digest);
  const responseText = await signed.text();
  assert.equal(responseText.includes(seen.key), false);

  const missingCsrf = await handleProxy({
    request: request("/api/session/v1/chat", {
      method: "POST",
      body: { message: "hi" },
      cookie: `resileos_session=${session.id}`,
    }),
    env,
    params: { path: ["chat"] },
    fetchImpl: async () => {
      throw new Error("upstream should not be called");
    },
    now: () => NOW,
  });
  assert.equal(missingCsrf.status, 403);
});

test("free key endpoint and logout do not return a raw key", async () => {
  const kv = memoryKv();
  const env = baseEnv(kv);
  const session = await createSession({ kv, env, email: "ada@example.com", now: NOW });
  const created = await handleFreeKey({
    request: request("/api/session/free-key", {
      method: "POST",
      cookie: `resileos_session=${session.id}`,
      headers: { "x-csrf-token": session.csrf },
    }),
    env,
    now: () => NOW,
  });
  assert.equal(created.status, 200);
  const body = await created.json();
  assert.equal(body.plan, "free");
  assert.equal(body.quota, 5000);
  assert.equal(body.api_key, undefined);
  const duplicate = await handleFreeKey({
    request: request("/api/session/free-key", {
      method: "POST",
      cookie: `resileos_session=${session.id}`,
      headers: { "x-csrf-token": session.csrf },
    }),
    env,
    now: () => NOW + 1,
  });
  assert.equal(duplicate.status, 409);

  const rotated = await handleRotate({
    request: request("/api/session/rotate", {
      method: "POST",
      cookie: `resileos_session=${session.id}`,
      headers: { "x-csrf-token": session.csrf },
    }),
    env,
    now: () => NOW + 2,
  });
  assert.equal(rotated.status, 200);
  assert.match(rotated.headers.get("set-cookie"), /Max-Age=0/);
  const loggedOut = await handleLogout({
    request: request("/api/session/logout", {
      method: "POST",
      cookie: rotated.headers.get("set-cookie"),
      headers: { "x-csrf-token": "unused" },
    }),
    env,
    now: () => NOW + 3,
  });
  assert.equal(loggedOut.status, 200);
});

test("password login sets a session cookie", async () => {
  const kv = memoryKv();
  const env = baseEnv(kv);
  await setPassword({
    kv, env, email: "ada@example.com", password: "correct horse", current: "", now: NOW, resetOk: true,
  });
  const stored = await hashPassword("correct horse", env);
  assert.equal(await verifyPassword("correct horse", stored), true);
  const res = await handleLogin({
    request: request("/api/session/login", {
      method: "POST",
      body: { email: "ada@example.com", password: "correct horse" },
    }),
    env,
    now: () => NOW,
  });
  assert.equal(res.status, 200);
  assert.match(res.headers.get("set-cookie"), /HttpOnly/);
  assert.match(res.headers.get("set-cookie"), /Secure/);
  assert.match(res.headers.get("set-cookie"), /SameSite=Lax/);
  const body = await res.json();
  assert.equal(body.api_key, undefined);
});
