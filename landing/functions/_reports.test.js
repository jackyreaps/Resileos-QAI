import assert from "node:assert/strict";
import { test } from "node:test";

import { createSession, memoryKv } from "./_auth.js";
import {
  adminEmails,
  decideProposal,
  handleReportsApprove,
  handleReportsList,
  handleReportsReject,
  isAdminEmail,
  saveReport,
} from "./_reports.js";

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

function sampleReport() {
  return {
    proposals: [
      {
        id: "p-review-1",
        kind: "new_module",
        target: "src/resileos/persona/promote.py",
        tier: "review",
        proposal_status: "pending",
        verification_status: "verified",
        writes_code: false,
      },
      {
        id: "p-auto-1",
        kind: "tighter_method",
        target: "tool_weights",
        tier: "auto",
        proposal_status: "auto_applied",
        verification_status: "verified",
        version: 1,
      },
    ],
    auto_log: [{ version: 1, target: "tool_weights", key: "search", status: "kept", reverted: false }],
  };
}

test("ADMIN_EMAILS is empty by default and ignores blanks", () => {
  assert.deepEqual(adminEmails({}), []);
  assert.deepEqual(adminEmails({ ADMIN_EMAILS: "" }), []);
  assert.deepEqual(adminEmails({ ADMIN_EMAILS: "  , ; \n" }), []);
  assert.equal(isAdminEmail("ops@example.com", {}), false);
  assert.deepEqual(
    adminEmails({ ADMIN_EMAILS: "Ops@example.com, other@example.com; OPS@example.com" }),
    ["ops@example.com", "other@example.com"]
  );
  assert.equal(isAdminEmail("OPS@example.com", { ADMIN_EMAILS: "ops@example.com" }), true);
});

test("unsigned and non-admin sessions cannot list or decide reports", async () => {
  const kv = memoryKv();
  const env = baseEnv(kv, { ADMIN_EMAILS: "ops@example.com" });
  await saveReport(kv, sampleReport());

  const unsigned = await handleReportsList({
    request: request("/api/session/reports"),
    env,
    now: () => NOW,
  });
  assert.equal(unsigned.status, 401);

  const empty = baseEnv(kv);
  const visitor = await createSession({ kv, env: empty, email: "visitor@example.com", now: NOW });
  const unset = await handleReportsList({
    request: request("/api/session/reports", { cookie: `resileos_session=${visitor.id}` }),
    env: empty,
    now: () => NOW,
  });
  assert.equal(unset.status, 403);
  const unsetBody = await unset.json();
  assert.equal(unsetBody.detail, "Admin access is not configured.");

  const user = await createSession({ kv, env, email: "visitor@example.com", now: NOW });
  const forbidden = await handleReportsList({
    request: request("/api/session/reports", { cookie: `resileos_session=${user.id}` }),
    env,
    now: () => NOW,
  });
  assert.equal(forbidden.status, 403);
  const forbiddenBody = await forbidden.json();
  assert.equal(forbiddenBody.detail, "Not an admin.");

  const approve = await handleReportsApprove({
    request: request("/api/session/reports/approve", {
      method: "POST",
      body: { id: "p-review-1" },
      cookie: `resileos_session=${user.id}`,
      headers: { "x-csrf-token": user.csrf },
    }),
    env,
    now: () => NOW,
    applyFn: () => {
      throw new Error("apply must not run for a non-admin");
    },
  });
  assert.equal(approve.status, 403);
});

test("an admin can list, approve, and reject, and approve does not apply code", async () => {
  const kv = memoryKv();
  const env = baseEnv(kv, { ADMIN_EMAILS: "ops@example.com" });
  await saveReport(kv, sampleReport());
  const admin = await createSession({ kv, env, email: "ops@example.com", now: NOW });
  const cookie = `resileos_session=${admin.id}`;

  const listed = await handleReportsList({
    request: request("/api/session/reports", { cookie }),
    env,
    now: () => NOW,
  });
  assert.equal(listed.status, 200);
  const body = await listed.json();
  assert.equal(body.proposals.length, 2);
  assert.equal(body.auto_log.length, 1);
  assert.equal(body.writes_code, false);
  assert.match(body.approved_to_pr, /out of scope/i);
  assert.match(body.email_digest, /future/i);
  assert.equal(body.proposals.some((item) => item.proposal_status === "pending"), true);
  assert.equal(body.proposals.some((item) => item.proposal_status === "auto_applied"), true);

  let applied = 0;
  const approved = await handleReportsApprove({
    request: request("/api/session/reports/approve", {
      method: "POST",
      body: { id: "p-review-1" },
      cookie,
      headers: { "x-csrf-token": admin.csrf },
    }),
    env,
    now: () => NOW,
    applyFn: () => {
      applied += 1;
      throw new Error("review approval must not apply code");
    },
  });
  assert.equal(approved.status, 200);
  const approvedBody = await approved.json();
  assert.equal(approvedBody.ok, true);
  assert.equal(approvedBody.applied, false);
  assert.equal(approvedBody.proposal.proposal_status, "approved");
  assert.equal(approvedBody.proposal.applied_on_approve, false);
  assert.equal(approvedBody.proposal.writes_code, false);
  assert.equal(applied, 0);

  const rejected = await handleReportsReject({
    request: request("/api/session/reports/reject", {
      method: "POST",
      body: { id: "p-auto-1" },
      cookie,
      headers: { "x-csrf-token": admin.csrf },
    }),
    env,
    now: () => NOW,
    applyFn: () => {
      applied += 1;
    },
  });
  assert.equal(rejected.status, 200);
  const rejectedBody = await rejected.json();
  assert.equal(rejectedBody.proposal.proposal_status, "rejected");
  assert.equal(applied, 0);

  const missingCsrf = await handleReportsApprove({
    request: request("/api/session/reports/approve", {
      method: "POST",
      body: { id: "p-review-1" },
      cookie,
    }),
    env,
    now: () => NOW,
  });
  assert.equal(missingCsrf.status, 403);
});

test("decideProposal never invokes applyFn", () => {
  const report = sampleReport();
  let called = false;
  const result = decideProposal(report, {
    id: "p-review-1",
    action: "approve",
    email: "ops@example.com",
    now: NOW,
    applyFn: () => {
      called = true;
    },
  });
  assert.equal(result.ok, true);
  assert.equal(result.applied, false);
  assert.equal(called, false);
  assert.equal(report.proposals[0].proposal_status, "approved");
});
