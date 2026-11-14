// Real-flow check of the email sign-in against the Pages functions with an in-memory KV.
// Usage: node landing/scripts/repro_signin_flow.mjs
import {
  handleLogin, handleLogout, handleMagicLink, handleMe, handlePassword, handleVerify, memoryKv,
} from "../functions/_auth.js";

const ORIGIN = "https://resileosai.fun";
let clock = 1_700_000_000_000;
const now = () => clock;
const kv = memoryKv();
const env = {
  KEYS: kv, EMAIL_FROM: "Resileos <login@resileosai.fun>", RESEND_API_KEY: "test-only",
  RESILEOS_SITE_URL: ORIGIN, SESSION_SECRET: "session-secret-value",
  KEY_SEAL_SECRET: "seal-secret-value-ok", RESILEOS_PROXY_SECRET: "proxy-secret-value",
  PASSWORD_PBKDF2_ITERATIONS: "100000",
};
const outbox = [];
const send = async (m) => { outbox.push(m); };
function req(path, { method = "GET", body, cookie = "", csrf = "" } = {}) {
  const headers = { origin: ORIGIN };
  if (cookie) headers.cookie = cookie;
  if (csrf) headers["x-csrf-token"] = csrf;
  const init = { method, headers };
  if (body !== undefined) { headers["content-type"] = "application/json"; init.body = JSON.stringify(body); }
  return new Request(ORIGIN + path, init);
}
const cookieOf = (res) => (res.headers.get("set-cookie") || "").split(";")[0];
const log = (step, res, extra = "") => console.log(`${step.padEnd(46)} ${res.status} ${res.headers.get("location") || ""} ${extra}`);

const email = "james@resileosai.fun";
let res = await handleMagicLink({ request: req("/api/session/magic-link", { method: "POST", body: { email, purpose: "login" } }), env, now, send });
log("1. magic link requested", res);
const link = outbox.at(-1).text.match(/https:\/\/\S+/)[0];
res = await handleVerify({ request: new Request(link), env, now });
log("2. magic link opened", res);
let cookie = cookieOf(res);
res = await handleMe({ request: req("/api/session/me", { cookie }), env, now, fetchImpl: async () => new Response("{}", { status: 404 }) });
const me = await res.json();
log("3. /me", res, `signed_in=${me.signed_in} has_password=${me.has_password}`);
clock += 1000;
res = await handlePassword({ request: req("/api/session/password", { method: "POST", cookie, csrf: me.csrf, body: { password: "a-good-password-1", current_password: "" } }), env, now });
log("4. set password (account page, blank current)", res);
res = await handleLogout({ request: req("/api/session/logout", { method: "POST", cookie, csrf: me.csrf }), env, now });
log("5. logout", res);
const attempts = [
  ["6a. login: exact email", { email, password: "a-good-password-1" }],
  ["6b. login: Mixed case + spaces", { email: "  James@ResileosAI.fun ", password: "a-good-password-1" }],
  ["6c. login: chat username in email box", { email: "james", password: "a-good-password-1" }],
  ["6d. login: email sent as `username` field", { username: email, password: "a-good-password-1" }],
  ["6e. login: password with trailing space", { email, password: "a-good-password-1 " }],
];
for (const [name, body] of attempts) {
  clock += 1000;
  const r = await handleLogin({ request: req("/api/session/login", { method: "POST", body }), env, now });
  const data = await r.clone().json();
  log(name, r, r.ok ? "signed in" : JSON.stringify(data.detail));
}
const rl = [...(await Promise.all([]))];
console.log("login rate-limit key present:", Boolean(await kv.get(`rl:login:ip:unknown:${Math.floor(clock / 3600000)}`)));
