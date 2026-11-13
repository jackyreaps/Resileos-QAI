# Upgrade proposals

Verified dream candidates can also be recorded as upgrade proposals
for an operator. The report is JSON plus a markdown summary. The
system never modifies its own code or config files from this path.

## Tiers

Classification uses an explicit allowlist and defaults to review.

Auto tier, only these bounded operational targets:

- `tool_weights`, `tool_preferences`
- `search_cache`, `crawl_cache`
- `source_quality_ranking`
- `metric_thresholds`, `tuning_params`

A change may apply automatically through `OperationalStore`. Each
change is versioned and gated on a named metric, and is auto-reverted
if that metric gets worse. Every change is logged on the report. Auto
tier still never touches code, config files, Eat, learn, scars,
Titanos, `require_verified`, or the Metis allow_mouth defaults.
Values outside the declared bounds are sent to review instead.

Declared bounds: weights, ranks, and thresholds in `[0, 1]`;
`tuning_params` in `[-8, 8]`; caches at most 256 entries and 4096
bytes per value.

Review tier: everything else, including `new_module`, `schema_change`,
learning or Eat changes, unknown targets, and unverified candidates.
These stay `pending` until a human approves or rejects them.

Search and crawl caches are a tuning interface on `OperationalStore`.
Hermes envelopes do not read them yet; hooking the cache into those
paths is left as a later change.

## Approval does not apply code

A review-tier approval only marks the proposal `approved` for a later
PR. It never applies code, writes a config file, or opens the PR.
Turning an approved proposal into a PR is out of scope and is done by
a person in the usual review process.

## How an operator reads the report

The admin-only view is `/admin/reports`, behind the existing session
sign-in (magic link or password, with the session-cookie proxy from
PR #33). The browser never holds an API key. Calls go to
`/api/session/reports`, `/api/session/reports/approve`, and
`/api/session/reports/reject`.

Access is gated by `ADMIN_EMAILS`, a comma-separated list of operator
addresses set in the Pages environment (and read by the session
functions). The list is empty by default, so the view stays closed
until it is set. Do not commit addresses in the repository.

The page lists pending review proposals and the auto-applied log, with
approve and reject actions.

A daily email digest of the same report is a future step, once email
sending is configured. It is not built in this change.

Operators can also write a report JSON into the `reports:upgrade` key
in the `KEYS` KV namespace; the admin view reads that document.

Code: `src/resileos/persona/upgrade_report.py`,
`src/resileos/persona/operational_tune.py`,
`landing/functions/_reports.js`.
