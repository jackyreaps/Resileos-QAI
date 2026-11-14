// End-to-end wiring: every user tool goes UI path -> Pages route -> API
// endpoint through the real handlers, with a fake backend standing in for
// the Python API. A missing route file or a broken proxy rule fails here.
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { test } from "node:test";

import { createSession, handleFreeKey, handleMe, handleProxy, handleReveal, handleRotate, memoryKv } from "./_auth.js";

const NOW = 1_700_000_000_000;
const HERE = new URL(".", import.meta.url);
const PUBLIC = new URL("../public/", import.meta.url);

function baseEnv(kv) {
  return {
    KEYS: kv,
    RESILEOS_SITE_URL: "https://resileosai.fun",
    RESILEOS_API_BASE_URL: "https://api.resileosai.fun/api/v1",
    SESSION_SECRET: "session-secret-value",
    KEY_SEAL_SECRET: "seal-secret-value-ok",
    RESILEOS_PROXY_SECRET: "proxy-secret-value",
    ADMIN_EMAILS: "james@resileosai.fun",
    FREE_KEY_RATE_PER_HOUR: "50",
  };
}

// Fake Python API: answers each endpoint the way the real one shapes it.
function fakeBackend() {
  const calls = [];
  const routes = {
    "POST /api/v1/assist": () => ({ value: "ok", assist: { trail: [{ label: "Looked at your image" }], sources: [{ title: "One", url: "https://one.example" }], learned: false } }),
    "POST /api/v1/chat": () => ({ value: "hello", status: "ACCEPTED" }),
    "POST /api/v1/verify/lean": () => ({ status: "FAILED", line: 2, summary: "Fails at line 2: rfl failed" }),
    "GET /api/v1/files": () => ({ files: [{ id: "a".repeat(32), name: "p.png" }], used: 9 }),
    "POST /api/v1/files": () => ({ id: "b".repeat(32), name: "n.txt", kind: "text" }),
    ["GET /api/v1/files/" + "a".repeat(32)]: () => new Response("PNGDATA", { status: 200, headers: { "content-type": "image/png", "content-disposition": 'attachment; filename="p.png"', "x-content-type-options": "nosniff", "cache-control": "private, no-store" } }),
    ["DELETE /api/v1/files/" + "a".repeat(32)]: () => ({ deleted: true }),
    "GET /api/v1/conversations": () => ({ conversations: [] }),
    "POST /api/v1/conversations": () => ({ id: "c1" }),
    "POST /api/v1/studio/forge/video": () => ({ status: "UNAVAILABLE", url: null }),
    "POST /api/v1/studio/video": () => ({ status: "drafted", preview: [[[0]]] }),
    "GET /api/v1/aphrodite/anon/state": () => ({ companion_prompt: "Welcome back." }),
    "GET /api/v1/ready": () => ({ ready: true }),
    "GET /api/v1/usage": () => ({ count: 1 }),
  };
  const fetchImpl = async (url, init = {}) => {
    const u = new URL(url);
    const key = `${init.method || "GET"} ${u.pathname}`;
    const headers = new Headers(init.headers);
    let body = null;
    if (init.body) body = await new Response(init.body).text();
    calls.push({ key, headers, body });
    const handler = routes[key];
    if (!handler) return new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 });
    const out = handler();
    return out instanceof Response ? out : new Response(JSON.stringify(out), { status: 200, headers: { "content-type": "application/json" } });
  };
  return { calls, fetchImpl };
}

function req(path, { method = "GET", body, raw, contentType, session } = {}) {
  const headers = { origin: "https://resileosai.fun" };
  if (session) {
    headers.cookie = `resileos_session=${session.id}`;
    headers["x-csrf-token"] = session.csrf;
  }
  const init = { method, headers };
  if (body !== undefined) {
    headers["content-type"] = "application/json";
    init.body = JSON.stringify(body);
  } else if (raw !== undefined) {
    headers["content-type"] = contentType;
    init.body = raw;
  }
  return new Request("https://resileosai.fun" + path, init);
}

async function via(env, backend, method, path, opts = {}) {
  return handleProxy({
    request: req("/api/session/v1/" + path, { method, ...opts }),
    env,
    params: { path: path.split("?")[0].split("/") },
    fetchImpl: backend.fetchImpl,
    now: () => NOW,
  });
}

async function setup() {
  const kv = memoryKv();
  const env = baseEnv(kv);
  const session = await createSession({ kv, env, email: "ada@example.com", now: NOW });
  return { kv, env, session };
}

const TOOLS = [
  // tool, method, path, body, page file that calls it, string in that file
  ["chat answer / upload perception / search / crawl / sources / create", "POST", "assist", { message: "hi", attachments: [{ name: "p.png", kind: "image", matrix: [[[0, 0, 0]]] }] }, "chat.html", "${apiUrl()}/assist"],
  ["chat (legacy direct)", "POST", "chat", { message: "hi" }, null, null],
  ["Lean check", "POST", "verify/lean", { source: "theorem t : 1 = 2 := rfl" }, null, null],
  ["Files list", "GET", "files", undefined, "assets/files.js", "/api/session/v1/files"],
  ["conversations", "GET", "conversations", undefined, "chat.html", "'/conversations'"],
  ["conversations save", "POST", "conversations", { messages: [] }, "chat.html", "'/conversations'"],
  ["Studio picture", "POST", "studio/forge/video", { prompt: "fox", stage: "draft" }, "assets/studio.js", '"/studio/forge/video"'],
  ["Studio clip", "POST", "studio/video", { prompt: "fox", stage: "draft", frames: [[[0]]] }, "assets/studio.js", '"/studio/video"'],
  ["persona / tutorial state", "GET", "aphrodite/anon/state", undefined, "chat.html", "/aphrodite/"],
  ["ready", "GET", "ready", undefined, "chat.html", "${apiUrl()}/ready"],
];

for (const [name, method, path, body, page, needle] of TOOLS) {
  test(`wiring: ${name} reaches ${method} /api/v1/${path} with the account key`, async () => {
    const { env, session } = await setup();
    const backend = fakeBackend();
    const res = await via(env, backend, method, path, { body, session });
    assert.equal(res.status, 200, await res.clone().text());
    assert.equal(backend.calls.length, 1);
    assert.equal(backend.calls[0].key, `${method} /api/v1/${path}`);
    assert.ok(backend.calls[0].headers.get("x-api-key"), "signed-in calls carry the sealed key");
    if (body !== undefined) assert.deepEqual(JSON.parse(backend.calls[0].body), body);
    await res.json();
    if (page) assert.ok(readFileSync(new URL(page, PUBLIC), "utf8").includes(needle), `${page} calls ${needle}`);
  });
}

test("wiring: signed-out chat tools get trial headers, not a key", async () => {
  const { env } = await setup();
  const backend = fakeBackend();
  const res = await via(env, backend, "POST", "assist", { body: { message: "hi" } });
  assert.equal(res.status, 200);
  assert.equal(backend.calls[0].headers.get("x-api-key"), null);
  assert.ok([...backend.calls[0].headers.keys()].some((h) => h.startsWith("x-resileos-trial")), [...backend.calls[0].headers.keys()].join(","));
});

test("wiring: Files upload passes multipart through untouched", async () => {
  const { env, session } = await setup();
  const backend = fakeBackend();
  const form = new FormData();
  form.append("file", new Blob(["hello"], { type: "text/plain" }), "n.txt");
  const probe = new Request("https://x/", { method: "POST", body: form });
  const raw = await probe.arrayBuffer();
  const res = await via(env, backend, "POST", "files", { raw, contentType: probe.headers.get("content-type"), session });
  assert.equal(res.status, 200);
  assert.match(backend.calls[0].headers.get("content-type"), /^multipart\/form-data; boundary=/);
  assert.match(backend.calls[0].body, /filename="n.txt"/);
  assert.equal((await res.json()).kind, "text");
});

test("wiring: Files download keeps attachment and nosniff headers; delete needs the page token", async () => {
  const { env, session } = await setup();
  const backend = fakeBackend();
  const id = "a".repeat(32);
  const got = await via(env, backend, "GET", `files/${id}`, { session });
  assert.equal(got.status, 200);
  assert.equal(got.headers.get("content-disposition"), 'attachment; filename="p.png"');
  assert.equal(got.headers.get("x-content-type-options"), "nosniff");
  assert.equal(got.headers.get("cache-control"), "private, no-store");
  assert.equal(await got.text(), "PNGDATA");
  const noToken = await handleProxy({
    request: new Request(`https://resileosai.fun/api/session/v1/files/${id}`, { method: "DELETE", headers: { origin: "https://resileosai.fun", cookie: `resileos_session=${session.id}` } }),
    env, params: { path: ["files", id] }, fetchImpl: backend.fetchImpl, now: () => NOW,
  });
  assert.equal(noToken.status, 403);
  const del = await via(env, backend, "DELETE", `files/${id}`, { session });
  assert.equal((await del.json()).deleted, true);
});

test("wiring: account key buttons (free key, rotate, reveal) and /me", async () => {
  const { env, session } = await setup();
  const call = (fn, path) => fn({ request: req(path, { method: "POST", body: {}, session }), env, now: () => NOW });
  const free = await call(handleFreeKey, "/api/session/free-key");
  assert.ok([200, 409].includes(free.status), String(free.status));
  const reveal = await call(handleReveal, "/api/session/reveal");
  assert.ok([200, 403].includes(reveal.status), String(reveal.status));
  const rotate = await call(handleRotate, "/api/session/rotate");
  assert.equal(rotate.status, 200);
  const me = await handleMe({ request: req("/api/session/me", { session }), env, now: () => NOW, fetchImpl: async () => new Response("{}") });
  assert.equal(me.status, 200);
});

test("wiring: every Pages route the pages call has a function file", () => {
  const routes = {
    "/api/session/me": "api/session/me.js",
    "/api/session/login": "api/session/login.js",
    "/api/session/magic-link": "api/session/magic-link.js",
    "/api/session/verify": "api/session/verify.js",
    "/api/session/logout": "api/session/logout.js",
    "/api/session/password": "api/session/password.js",
    "/api/session/free-key": "api/session/free-key.js",
    "/api/session/rotate": "api/session/rotate.js",
    "/api/session/reveal": "api/session/reveal.js",
    "/api/session/reports": "api/session/reports.js",
    "/api/session/reports/approve": "api/session/reports/approve.js",
    "/api/session/reports/reject": "api/session/reports/reject.js",
    "/api/create-checkout-session": "api/create-checkout-session.js",
    "/api/config": "api/config.js",
    "/api/claim/": "api/claim/[session_id].js",
    "/api/session/v1/": "api/session/v1/[[path]].js",
    "/admin": "admin/_middleware.js",
  };
  for (const [route, file] of Object.entries(routes)) {
    assert.ok(existsSync(new URL(file, HERE)), `${route} -> ${file}`);
  }
  for (const page of ["chat.html", "studio.html", "files.html", "account.html", "login.html", "admin/index.html", "admin/reports.html", "admin/knowledge.html", "admin/diagnostics.html"]) {
    assert.ok(existsSync(new URL(page, PUBLIC)), page);
  }
});
