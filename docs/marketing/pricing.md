---
doc: MKT-001
title: Pricing and packaging
status: stable
depends_on: [RES-320]
referenced_by: [MKT-002]
---

# Pricing and packaging (internal)

Source of truth for tiers, quotas, and what may be sold. The landing page is a
rendering of this document; when they disagree, this document wins.

## 1. Principles

1. Charge for hosting, seats, quota, and storage — never for Merit.
2. Credits stay internal. They may later burn for optional compute; they are
   never sold and never convert to Merit or fiat in-product.
3. The free tier is real but rate-limited, so it markets the API without
   funding abuse.
4. Price maps onto the `tier` field already enforced by `middleware/auth.py`
   and `app.py`.

## 2. Tiers

| | Free | Builder | Team | Org |
|---|---|---|---|---|
| Price | $0 | $29/mo | $99/mo | Custom |
| API keys | 1 | 3 | 10 | Custom |
| Requests / month | 5,000 | 100,000 | 500,000 | Committed |
| Overage | hard 429 | $0.50 / 10k | $0.40 / 10k | negotiated |
| Hubs | Personal + `world:` | Shared worlds | Multi-guild | Unlimited |
| Guild workspace | 1 / 3 members | 1 / 15 members | 3 / 50 members | Unlimited* |
| Durable state | best-effort | durable volume | + daily snapshot | multi-region |
| Optional mouth | structured only | + small RAG budget | higher budget | BYO key / dedicated |
| Support | docs | email | priority email | Slack / contract |
| Uptime commitment | none | none | 99.5% **target** | negotiated |

\* Fair use. Abuse throttled.

`99.5% target` is an internal goal. It is not an SLA. It may only be described as
a commitment after a status page exists and has 90 days of measured data.

## 3. Surface gating

A tier row may only be sold when the route behind it is mounted on the deployed
host and has passed a production smoke test.

| Surface | Route | Sellable now? |
|---|---|---|
| Learn / batch / query / chain / SPARQL / answer | `/api/v1/*` | Yes |
| Tool schemas | `GET /api/v1/tools` | Yes |
| Substrate train / verify / sweep | `/api/v1/*` | Yes |
| leCore router | `/api/v1/lecore/*` | Yes |
| World asset registry | `/api/v1/world/*` | **No** |
| Guild workspace | `/api/v1/guild/*` | **No** |

When a surface moves to "Yes", update this table, remove the corresponding
`soon` badge in `landing/index.html`, and only then price the row.

## 4. Founding Builder

- $19/mo, locked for 12 months
- Capped at 50 customers
- Hard seat limit: 1 workspace, 3 API keys
- Fixed end date on the invoice (for example 2027-11-01)
- Renewal is at standard Builder price; the founding rate does not auto-renew

## 5. Add-ons (margin)

| Add-on | Price |
|---|---|
| Extra request pack | $5 / 25,000 calls |
| Extra storage | $2 / GB / month (state + asset index) |
| Dedicated instance | from $249/mo |
| Verify hook capacity | metered external-checker minutes |

Verify hook capacity is compute, not an attestation service. Do not describe it
as a legal or compliance guarantee.

## 6. What is never sold

- Merit points
- Peer attestation as a SKU
- "Sovereign network" access as a product
- Credits → cash conversion in-product
- Media hosting, transcoding, or streaming

## 7. Tier → key mapping

| Plan | `tier` in key record | `quota` |
|---|---|---|
| Free | `free` | 5000 |
| Builder | `pro` | 100000 |
| Team | `pro` | 500000 |
| Org | `enterprise` | 0 (unlimited) |

`quota` is an integer in the key record. Overage must be handled by a separate
billing path, not by exceeding the integer.

## 8. Metrics required before price changes

Read from `artifacts/report_ops_metrics.json` and the published artifacts:

- `M1_tool_honesty.rate` = 1.0
- `M2_invention_rate.rate` = 0.0
- `M4_hub_durability.rate` = 1.0 after a real restart
- p50 and p95 latency for `/query` and `/learn`
- Measured uptime over at least 90 days (required before any uptime wording)

## 9. Stripe wiring

1. Products: `builder_monthly`, `team_monthly`, `org_custom`.
2. Checkout success → write the customer's hashed key with the correct `tier`
   and `quota` (file today, database when the file becomes the bottleneck).
3. `customer.subscription.deleted` → downgrade `tier` to `free`; retain data for
   30 days before deletion.
4. Monthly usage push: read `/app/data/usage.json`, send usage records, then
   reset the monthly bucket.
5. Verify webhook signatures with `STRIPE_WEBHOOK_SECRET`.

## 10. Packaging narrative

| Buyer | Lead with | Entry tier |
|---|---|---|
| Solo builder / researcher | Exact learn/query API, no retraining | Free → Builder |
| Small lab or studio | Shared worlds + one guild board | Builder → Team |
| Collective / pilot guild | Seats, ledger durability, board | Team |
| Company | SLA path, SSO, private deployment | Org |
