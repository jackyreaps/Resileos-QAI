/** Admin-only upgrade-report view, gated by ADMIN_EMAILS.

The list, approve, and reject routes sit behind the existing session
cookie (magic link or password). The browser never holds an API key.
ADMIN_EMAILS is a comma or whitespace separated list, empty by default,
so nothing is exposed until an operator sets it. Review-tier approval
only marks a proposal approved for a later PR; it never applies code.
*/
import { detail, json } from "./_lib.js";
import { csrfOk, originAllowed, readSession } from "./_auth.js";
import { adminEmails, isAdminEmail } from "./_admin.js";

export const REPORT_KEY = "reports:upgrade";

function momentOf(now) {
  return typeof now === "function" ? now() : Date.now();
}

function noStore(response) {
  response.headers.set("Cache-Control", "no-store");
  return response;
}

export { adminEmails, isAdminEmail };

export function emptyReport() {
  return {
    proposals: [],
    auto_log: [],
    writes_code: false,
    writes_config: false,
    writes_titanos: false,
    learned: false,
    approved_to_pr: "out of scope: a human-approved review item becomes a normal PR",
    email_digest: "future: optional daily digest once email sending is configured",
  };
}

export async function loadReport(kv) {
  const raw = await kv.get(REPORT_KEY);
  const report = emptyReport();
  if (!raw) return report;
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed.proposals)) report.proposals = parsed.proposals;
    if (Array.isArray(parsed.auto_log)) report.auto_log = parsed.auto_log;
  } catch {
    /* keep the empty report rather than failing the page */
  }
  return report;
}

export async function saveReport(kv, report) {
  const body = {
    ...emptyReport(),
    proposals: report.proposals || [],
    auto_log: report.auto_log || [],
  };
  await kv.put(REPORT_KEY, JSON.stringify(body));
  return body;
}

async function requireAdmin({ request, env, now, mutating }) {
  if (mutating && !originAllowed(request, env)) {
    return { response: detail("Cross-site request blocked.", 403) };
  }
  const kv = env && env.KEYS;
  if (!kv) return { response: detail("Key storage is not bound.", 503) };
  const clock = momentOf(now);
  const session = await readSession({ kv, env, request, now: clock });
  if (!session) return { response: detail("You're signed out. Sign in again to continue.", 401) };
  if (mutating && !csrfOk(request, session.record)) {
    return { response: detail("This page is out of date. Refresh it and try again.", 403) };
  }
  if (!adminEmails(env).length) {
    return { response: detail("Admin access is not configured.", 403) };
  }
  if (!isAdminEmail(session.email, env)) {
    return { response: detail("This page is for site admins only. You're signed in with an address that isn't on the admin list.", 403) };
  }
  return { kv, session, now: clock };
}

async function readJson(request) {
  try {
    return await request.json();
  } catch {
    return {};
  }
}

export async function handleReportsList({ request, env, now }) {
  const gate = await requireAdmin({ request, env, now, mutating: false });
  if (gate.response) return gate.response;
  const report = await loadReport(gate.kv);
  return noStore(json(report));
}

export function decideProposal(report, { id, action, email, now, applyFn }) {
  const status = action === "approve" ? "approved" : action === "reject" ? "rejected" : "";
  if (!status) return { ok: false, status: 400, detail: "Unknown action." };
  const proposal = (report.proposals || []).find((item) => item && item.id === id);
  if (!proposal) return { ok: false, status: 404, detail: "Unknown proposal." };
  // Review-tier approval (and every other approve) only marks status.
  // Nothing is applied: no code, no config, no Eat, no learn, no Titanos.
  if (typeof applyFn === "function") {
    /* applyFn is accepted so tests can prove it is never invoked */
  }
  proposal.proposal_status = status;
  proposal.decided_at = new Date(now).toISOString();
  if (email) proposal.decided_by = email;
  proposal.applied_on_approve = false;
  proposal.writes_code = false;
  proposal.writes_config = false;
  proposal.writes_titanos = false;
  proposal.learned = false;
  return { ok: true, applied: false, proposal };
}

async function handleDecide({ request, env, now, action, applyFn }) {
  const gate = await requireAdmin({ request, env, now, mutating: true });
  if (gate.response) return gate.response;
  const body = await readJson(request);
  const id = typeof body.id === "string" ? body.id.trim() : "";
  if (!id) return detail("Proposal id is required.", 400);
  const report = await loadReport(gate.kv);
  const result = decideProposal(report, {
    id,
    action,
    email: gate.session.email,
    now: gate.now,
    applyFn,
  });
  if (!result.ok) return detail(result.detail, result.status);
  await saveReport(gate.kv, report);
  return noStore(json({ ok: true, applied: false, proposal: result.proposal }));
}

export async function handleReportsApprove(context) {
  return handleDecide({ ...context, action: "approve" });
}

export async function handleReportsReject(context) {
  return handleDecide({ ...context, action: "reject" });
}
