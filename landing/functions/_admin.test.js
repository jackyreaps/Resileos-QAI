import assert from "node:assert/strict";
import { test } from "node:test";

import { handleAdminPage, isAdminEmail, publicApiAllowed } from "./_admin.js";
import { createSession, handleMe, handleProxy, memoryKv } from "./_auth.js";

const NOW = 1_700_000_000_000;
const ADMIN = "james@resileosai.fun";

function baseEnv(kv, extra = {}) {
  return {
    KEYS: kv,
    RESILEOS_SITE_URL: "https://resileosai.fun",
    RESILEOS_API_BASE_URL: "https://api.resileosai.fun/api/v1",
    SESSION_SECRET: "session-secret-value",
    KEY_SEAL_SECRET: "seal-secret-value-ok",
    RESILEOS_PROXY_SECRET: "proxy-secret-value",
    ADMIN_EMAILS: ADMIN,
    ...extra,
  };
}

function request(path, { method = "GET", body, cookie = "", csrf = "" } = {}) {
  const headers = { origin: "https://resileosai.fun" };
  if (cookie) headers.cookie = cookie;
  if (csrf) headers["x-csrf-token"] = csrf;
  const init = { method, headers };
  if (body !== undefined) {
    headers["content-type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  return new Request("https://resileosai.fun" + path, init);
}

function upstreamSpy() {
  const calls = [];
  const fetchImpl = async (url) => {
    calls.push(url);
    return new Response("{}", { status: 200, headers: { "content-type": "application/json" } });
  };
  return { calls, fetchImpl };
}

async function proxy(env, method, path, { session, body, fetchImpl } = {}) {
  const parts = path.split("?")[0].split("/").filter(Boolean);
  return handleProxy({
    request: request("/api/session/v1/" + path, {
      method,
      body,
      cookie: session ? `resileos_session=${session.id}` : "",
      csrf: session ? session.csrf : "",
    }),
    env,
    params: { path: parts },
    fetchImpl,
    now: () => NOW,
  });
}

test("publicApiAllowed lets through only what chat and Studio use", () => {
  const allowed = [
    ["GET", "ready"], ["GET", "usage"], ["POST", "chat"], ["POST", "assist"], ["POST", "verify/lean"],
    ["GET", "files"], ["POST", "files"], ["GET", "files/0123456789abcdef0123456789abcdef"], ["DELETE", "files/0123456789abcdef0123456789abcdef"],
    ["GET", "conversations"], ["POST", "conversations"], ["GET", "conversations/abc123"], ["PUT", "conversations/abc123"],
    ["POST", "studio/forge/video"], ["POST", "studio/video"], ["POST", "generate/video"],
    ["GET", "aphrodite/anon/state"], ["HEAD", "ready"],
  ];
  for (const [method, path] of allowed) {
    assert.equal(publicApiAllowed(method, path.split("/")), true, `${method} ${path} should be public`);
  }
  const denied = [
    ["POST", "studio/graphify"], ["POST", "kin/cycle"], ["POST", "kin/separated_cycle"], ["GET", "kin/hades/list"],
    ["POST", "kin/hades/restore"], ["POST", "eat/preview"], ["POST", "council/query"], ["GET", "tools"],
    ["POST", "tools/residual_consistency"], ["GET", "hub/anon/ledger"], ["PUT", "hub/anon/ledger"], ["DELETE", "hub/anon/ledger"],
    ["POST", "perceive/language"], ["POST", "studio/stop"], ["POST", "studio/plan-test-debug"], ["GET", "studio/codecs"],
    ["POST", "aphrodite/anon/preference"], ["POST", "aphrodite/anon/reset"], ["DELETE", "conversations/abc123"],
    ["POST", "ready"], ["GET", "conversations/../tools"], ["POST", "studio/video/restore"],
    ["POST", "upload"], ["PUT", "files/abc"], ["POST", "verify_manifold"], ["POST", "learn"], ["POST", "persona/promote"],
  ];
  for (const [method, path] of denied) {
    assert.equal(publicApiAllowed(method, path.split("/")), false, `${method} ${path} should be admin-only`);
  }
});

test("admin endpoints: 401 signed out, 403 for regular accounts, allowed for admins", async () => {
  const kv = memoryKv();
  const env = baseEnv(kv);
  const user = await createSession({ kv, env, email: "ada@example.com", now: NOW });
  const admin = await createSession({ kv, env, email: ADMIN, now: NOW });
  const paths = [
    ["POST", "studio/graphify", { source: "Alice works at Acme.", commit: true }],
    ["POST", "kin/cycle", { apply_policy: true, user_id: "anon" }],
    ["POST", "eat/preview", { claim: { subject: "a", relation: "b", obj: "c" } }],
    ["DELETE", "hub/anon/ledger?relation=prefers&obj=tea", undefined],
    ["GET", "tools", undefined],
  ];
  for (const [method, path, body] of paths) {
    const spy = upstreamSpy();
    const anon = await proxy(env, method, path, { body, fetchImpl: spy.fetchImpl });
    assert.equal(anon.status, 401, `${path} signed out`);
    const regular = await proxy(env, method, path, { session: user, body, fetchImpl: spy.fetchImpl });
    assert.equal(regular.status, 403, `${path} regular user`);
    assert.match((await regular.json()).detail, /admins/);
    assert.equal(spy.calls.length, 0, `${path} must not reach the API for non-admins`);
    const ok = await proxy(env, method, path, { session: admin, body, fetchImpl: spy.fetchImpl });
    assert.notEqual(ok.status, 401, `${path} admin`);
    assert.notEqual(ok.status, 403, `${path} admin`);
    assert.equal(spy.calls.length, 1, `${path} admin reaches the API`);
  }
});

test("public chat and Studio calls still work signed out and for regular accounts", async () => {
  const kv = memoryKv();
  const env = baseEnv(kv);
  const user = await createSession({ kv, env, email: "ada@example.com", now: NOW });
  for (const [method, path, body] of [
    ["POST", "chat", { message: "hi" }],
    ["POST", "studio/forge/video", { prompt: "a fox", stage: "draft" }],
    ["POST", "studio/video", { prompt: "waves", stage: "draft" }],
    ["GET", "ready", undefined],
  ]) {
    const spy = upstreamSpy();
    const anon = await proxy(env, method, path, { body, fetchImpl: spy.fetchImpl });
    assert.equal(anon.status, 200, `${path} signed out`);
    const signed = await proxy(env, method, path, { session: user, body, fetchImpl: spy.fetchImpl });
    assert.equal(signed.status, 200, `${path} regular user`);
    assert.equal(spy.calls.length, 2);
  }
});

test("no admin list means nobody is an admin", async () => {
  const kv = memoryKv();
  const env = baseEnv(kv, { ADMIN_EMAILS: "" });
  assert.equal(isAdminEmail(ADMIN, env), false);
  const session = await createSession({ kv, env, email: ADMIN, now: NOW });
  const res = await proxy(env, "POST", "kin/cycle", { session, body: {}, fetchImpl: upstreamSpy().fetchImpl });
  assert.equal(res.status, 403);
});

test("/me says whether the account is an admin", async () => {
  const kv = memoryKv();
  const env = baseEnv(kv);
  const fetchImpl = async () => new Response("{}", { status: 200 });
  for (const [email, expected] of [[ADMIN, true], ["ada@example.com", false]]) {
    const session = await createSession({ kv, env, email, now: NOW });
    const res = await handleMe({ request: request("/api/session/me", { cookie: `resileos_session=${session.id}` }), env, now: () => NOW, fetchImpl });
    const body = await res.json();
    assert.equal(body.signed_in, true);
    assert.equal(body.admin, expected, email);
  }
  const anon = await handleMe({ request: request("/api/session/me"), env, now: () => NOW, fetchImpl });
  const body = await anon.json();
  assert.equal(body.signed_in, false);
  assert.notEqual(body.admin, true);
});

test("/admin pages: sign-in redirect, 403 for regular accounts, served to admins", async () => {
  const kv = memoryKv();
  const env = baseEnv(kv);
  const next = async () => new Response("<h1>admin</h1>", { status: 200, headers: { "content-type": "text/html" } });
  const anon = await handleAdminPage({ request: request("/admin/knowledge"), env, next, now: () => NOW });
  assert.equal(anon.status, 302);
  assert.equal(anon.headers.get("location"), "/login?next=%2Fadmin%2Fknowledge");
  const user = await createSession({ kv, env, email: "ada@example.com", now: NOW });
  const regular = await handleAdminPage({ request: request("/admin/knowledge", { cookie: `resileos_session=${user.id}` }), env, next, now: () => NOW });
  assert.equal(regular.status, 403);
  assert.match(await regular.text(), /Admins only/);
  const admin = await createSession({ kv, env, email: ADMIN, now: NOW });
  const ok = await handleAdminPage({ request: request("/admin/knowledge", { cookie: `resileos_session=${admin.id}` }), env, next, now: () => NOW });
  assert.equal(ok.status, 200);
  assert.equal(ok.headers.get("cache-control"), "no-store");
  assert.match(await ok.text(), /admin/);
});
