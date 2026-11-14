/** Who is an admin, and which API calls a regular visitor may make.

ADMIN_EMAILS is a comma or whitespace separated list, empty by default.
The session proxy (/api/session/v1/*) lets regular visitors reach only the
calls the public chat and Studio use. Everything else (adding facts,
learning cycles, memory edits, checkpoints, raw tools, perception and codec
diagnostics) is admin-only, checked on the server for every request.
*/
import { normalizeEmail, sessionEmail } from "./_auth.js";

export function adminEmails(env) {
  const raw = String((env && env.ADMIN_EMAILS) || "");
  const out = [];
  const seen = new Set();
  for (const part of raw.split(/[,;\s]+/)) {
    const email = normalizeEmail(part);
    if (!email || seen.has(email)) continue;
    seen.add(email);
    out.push(email);
  }
  return out;
}

export function isAdminEmail(email, env) {
  const want = normalizeEmail(email);
  if (!want) return false;
  return adminEmails(env).includes(want);
}

const SEGMENT = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;

/* method -> list of path patterns. "*" matches one safe path segment. */
const PUBLIC_API = [
  ["GET", ["ready"]],
  ["GET", ["usage"]],
  ["POST", ["chat"]],
  ["POST", ["assist"]],
  ["POST", ["chat", "stream"]],
  ["GET", ["chat", "stream", "*"]],
  ["POST", ["chat", "stream", "*", "cancel"]],
  ["POST", ["verify", "lean"]],
  ["GET", ["files"]],
  ["POST", ["files"]],
  ["GET", ["files", "*"]],
  ["DELETE", ["files", "*"]],
  ["GET", ["conversations"]],
  ["POST", ["conversations"]],
  ["GET", ["conversations", "*"]],
  ["PUT", ["conversations", "*"]],
  ["POST", ["studio", "forge", "video"]],
  ["POST", ["studio", "video"]],
  ["POST", ["studio", "variations"]],
  ["POST", ["studio", "clip-from-picture"]],
  ["POST", ["generate", "video"]],
  ["GET", ["aphrodite", "*", "state"]],
  ["POST", ["aphrodite", "*", "state"]],
];

export function publicApiAllowed(method, parts) {
  const verb = String(method || "").toUpperCase();
  const want = verb === "HEAD" ? "GET" : verb;
  const path = Array.isArray(parts) ? parts.map(String) : [];
  return PUBLIC_API.some(([m, pattern]) => {
    if (m !== want || pattern.length !== path.length) return false;
    return pattern.every((piece, i) => (piece === "*" ? SEGMENT.test(path[i]) : piece === path[i]));
  });
}

const ADMIN_ONLY_PAGE = `<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Admins only — Resileos</title><link rel="stylesheet" href="/assets/site.css" /></head>
<body><main id="main" style="max-width:36rem;margin:0 auto;padding:120px 20px">
<h1>Admins only</h1><p class="lede">This page is for site admins. You're signed in with an account that isn't one.</p>
<p class="cta-row"><a class="btn btn-primary" href="/chat">Go to chat</a> <a class="btn btn-ghost" href="/account">Account</a></p>
</main></body></html>`;

/* Gate for the static /admin pages. The admin API calls are enforced in
 * handleProxy and the reports handlers; this keeps the pages themselves
 * from loading for anyone else. */
export async function handleAdminPage({ request, env, next, now }) {
  const email = await sessionEmail(request, env, now);
  if (!email) {
    const url = new URL(request.url);
    const target = url.pathname.replace(/\.html$/, "") || "/admin";
    return new Response(null, {
      status: 302,
      headers: { Location: "/login?next=" + encodeURIComponent(target), "Cache-Control": "no-store" },
    });
  }
  if (!isAdminEmail(email, env)) {
    return new Response(ADMIN_ONLY_PAGE, {
      status: 403,
      headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
    });
  }
  const res = await next();
  const out = new Response(res.body, res);
  out.headers.set("Cache-Control", "no-store");
  return out;
}
