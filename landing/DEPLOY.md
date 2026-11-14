# Deploy Resileos landing + billing

This folder is the landing and billing stack in `Resileos-QAI`. Do not commit
secrets.

## Architecture

| Piece | Role | Typical host |
|---|---|---|
| `public/` | Static marketing site | Cloudflare Pages, Netlify, Vercel, or GitHub Pages |
| `api/server.py` | Free-key mint, Stripe Checkout, webhook, claim | Fly.io, Railway, Render, or same VPS as the Resileos API |
| Resileos API (`asgi:app`) | Learn / query / chain | Your existing Docker / tunnel host |

Locally, one process serves both: `uvicorn` loads `api.server:app`, which also
serves `public/`.

## 1. Stripe products (test mode first)

### Automated (recommended)

```bash
export STRIPE_SECRET_KEY
pip install stripe
python scripts/stripe_setup.py
# paste printed STRIPE_PRICE_* lines into .env
```

`STRIPE_SECRET_KEY` must be a test-mode secret for local runs. Idempotent:
reuses products and prices tagged with `metadata.resileos_plan`. The same
script accepts a live-mode secret when you are ready to go live. Do not write
either value into git.

### Manual


1. Create a [Stripe](https://dashboard.stripe.com) account.
2. Switch to **Test mode**.
3. Products → Add product:
   - **Builder** — recurring monthly **$29** → copy Price ID → `STRIPE_PRICE_BUILDER`
   - **Founding Builder** — recurring monthly **$19** → `STRIPE_PRICE_FOUNDING_BUILDER` (optional; cap sales yourself)
   - **Team** — recurring monthly **$99** → `STRIPE_PRICE_TEAM`
4. Developers → API keys → Secret key → `STRIPE_SECRET_KEY` (test mode for local runs).
5. Developers → Webhooks → Add endpoint:
   - URL: `https://<billing-host>/api/stripe/webhook`
   - Events: `checkout.session.completed`, `customer.subscription.deleted`
   - Signing secret → `STRIPE_WEBHOOK_SECRET`
6. (Fallback) Payment Links for Builder / Team → set
   `STRIPE_PAYMENT_LINK_BUILDER` / `STRIPE_PAYMENT_LINK_TEAM`. The site uses
   these if Checkout session creation fails.

Prices come from `docs/marketing/pricing.md` in the main repo (Free $0,
Builder $29, Team $99, Org custom, Founding Builder $19).

## 2. Environment

Copy `.env.example` and fill values:

```bash
cp .env.example .env
# edit .env — never commit it
export $(grep -v '^#' .env | xargs)   # or use your host's secret store
```

Required for payments:

- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_BUILDER` (and Team / Founding as needed)
- `RESILEOS_API_BASE_URL` — the real Resileos `/api/v1` base shown to users
- `API_KEYS_PATH` — JSON file shared with (or synced to) the Resileos API host

Optional:

- `STRIPE_PAYMENT_LINK_*` — no-backend fallback
- `RESILEOS_LANDING_ORIGIN` — CORS allowlist (default `*`)
- `FREE_KEY_RATE_PER_HOUR` — default 5

## 3. Run locally

```bash
cd landing
python3 -m venv .venv && source .venv/bin/activate
pip install -r api/requirements.txt
mkdir -p data
export API_KEYS_PATH=./data/api_keys.json
export RESILEOS_API_BASE_URL=http://127.0.0.1:8000/api/v1
export RESILEOS_SITE_URL=http://127.0.0.1:8787
uvicorn api.server:app --app-dir . --host 127.0.0.1 --port 8787 --reload
```

Open http://127.0.0.1:8787

- Free key: form → `POST /api/free-key` → key + curls.
- Stripe: without keys, Checkout buttons show a clear error; Payment Links work if set.
- Forward webhooks in test mode: `stripe listen --forward-to localhost:8787/api/stripe/webhook`

## 4. Wire keys into Resileos-QAI

Minted records match `configs/api_keys.json`:

```json
{
  "<sha256-hex>": {
    "name": "free",
    "tier": "free",
    "quota": 5000,
    "plan": "free",
    "email": null,
    "created_at": "…"
  }
}
```

Tier mapping (pricing.md §7): Free→`free`/5000 · Builder/Team→`pro` · Org→`enterprise`/0.

Point the API container at the same file:

```yaml
environment:
  - API_KEYS_PATH=/app/configs/api_keys.json
volumes:
  - ./data/api_keys.json:/app/configs/api_keys.json
```

Or sync on webhook. Resileos reloads keys from disk per request (no restart needed for file updates).

## 5. Static-only hosting + separate API

If Pages/Netlify serves only `public/`:

1. Deploy `api/server.py` elsewhere.
2. In `public/index.html`, set before `site.js`:

```html
<script>window.RESILEOS_BILLING = "https://billing.yourdomain.dev";</script>
```

3. Set `RESILEOS_LANDING_ORIGIN` on the API to your Pages origin.


## 5a. Cloudflare Pages (current live deploy)

The marketing site is deployed as Cloudflare Pages project `resileos`.

- Production URL: https://resileos.pages.dev
- Custom domains: https://resileosai.fun and https://www.resileosai.fun
- Static assets: `public/` (exclude `public/assets/gods/cc0/`)
- Functions: `functions/api/config.js`, `free-key.js`, `create-checkout-session.js`, `claim/[session_id].js`, and `functions/api/session/*` (magic link, password, account, proxy, admin reports)
- KV namespace `resileos-keys` bound as `KEYS` (hashed key records, sealed key material, sessions, email and IP limits, one-time claim)
- Plaintext env: `STRIPE_PRICE_*`, `STRIPE_SUCCESS_URL`, `STRIPE_CANCEL_URL`, `RESILEOS_SITE_URL`, `RESILEOS_API_BASE_URL=https://api.resileosai.fun/api/v1`, `FREE_KEY_RATE_PER_HOUR`, `MAGIC_LINK_TTL_SECONDS` (900), `SESSION_TTL_SECONDS` (1209600), `PASSWORD_PBKDF2_ITERATIONS` (100000)
- Encrypted secrets: `STRIPE_SECRET_KEY`, `SESSION_SECRET`, `KEY_SEAL_SECRET`, `RESILEOS_PROXY_SECRET`, and one email provider (below)
- Success URL: `https://resileosai.fun/chat?checkout=success`
- Cancel URL: `https://resileosai.fun/#pricing` (the homepage forwards that hash to `/pricing`. Do not add a `/chat` → `/chat.html` rewrite.)
- Claim does not require a webhook: it retrieves the Checkout Session from Stripe, mints once, and stores the hash in KV. A signed-in browser attaches that key to the account and does not receive the raw key. `?delivery=key` still returns the raw key once for a script.
- Redeploy from the `landing/` directory: `npx wrangler pages deploy public --project-name resileos`

## 5b. Sign-in, account keys, and the API directory

The browser holds an `HttpOnly; Secure; SameSite=Lax` cookie named `resileos_session`. Chat and account calls go to `/api/session/*` on this site. The proxy adds `X-API-Key` from a sealed copy in KV. The API stores and validates only the SHA-256 digest.

Quotas, per calendar month on the API host clock:

| Plan | tier | monthly quota |
|---|---|---|
| Free (`TIER_QUOTA.free`) | `free` | 5000 |
| Builder $29/mo | `pro` | 100000 |
| Founding Builder $19/mo | `pro` | 100000 |
| Team $99/mo | `pro` | 500000 |
| Org | `enterprise` | 0 (unlimited) |

Signed-out chat is not a shared key. The proxy proves the client IP with HMAC. The API allows `RESILEOS_TRIAL_DAILY_LIMIT` requests per IP per UTC day (default 20), then chat asks the visitor to sign in.

### Secrets and bindings the owner must set

Pages → project `resileos` → Settings → Variables and secrets. Do not commit the values.

| Name | Where | Required |
|---|---|---|
| `SESSION_SECRET` | Pages secret, 16+ random characters | yes, or sign-in returns 503 `session secret not configured` |
| `KEY_SEAL_SECRET` | Pages secret, different from the session secret | yes, or key creation returns 503 `key seal is not configured` |
| `RESILEOS_PROXY_SECRET` | Pages secret **and** the API container, same value | yes for the anonymous trial |
| `EMAIL_FROM` | Pages plaintext, address on a domain you send from, e.g. `login@resileosai.fun` | yes to send mail |
| Email provider | one of the two below | yes, or `POST /api/session/magic-link` returns 503 `email not configured` and does not send |
| `CLOUDFLARE_API_TOKEN` | API host only. Token scope **Account → Workers KV Storage → Read** | yes for the API to accept Pages keys |
| `CLOUDFLARE_ACCOUNT_ID` | API host | yes with the token |
| `CLOUDFLARE_KV_NAMESPACE_ID` | API host. This namespace is `463f5f1f1d0a484fb3b9a8e79f0fc413` | yes with the token |
| `RESILEOS_KV_CACHE_TTL` | API host, seconds, default 30 | optional |
| `RESILEOS_TRIAL_DAILY_LIMIT` | API host, default 20 | optional |
| `ADMIN_EMAILS` | Pages env, comma-separated operator addresses, empty by default | optional; leave unset and `/admin/reports` stays closed. Do not commit addresses in the repo |

Email, pick one:

1. Cloudflare Email Sending. Onboard the domain, then add this binding and redeploy:

```toml
[[send_email]]
name = "EMAIL"
```

The binding name must be `EMAIL`. `EMAIL_FROM` must be an address on that domain.

2. Otherwise set `RESEND_API_KEY` (or `EMAIL_API_KEY`). Optional `EMAIL_API_URL` defaults to `https://api.resend.com/emails`. A Cloudflare Email Sending token can be used instead of the binding: `CLOUDFLARE_EMAIL_API_TOKEN` plus `CLOUDFLARE_ACCOUNT_ID` on Pages. That token is separate from the KV read token.

Password hashes are PBKDF2-SHA256, 16-byte salt, 100000 iterations. That is the most Cloudflare Workers allow, so `PASSWORD_PBKDF2_ITERATIONS` is ignored and kept at 100000.

Sign-in is one page, `/login`, used by chat, Account, and `/admin/reports` (each sends `?next=`). Enter an email, then either "Continue with password" or "Email me a link". A first link sign-in on an account with no password offers an optional "Set a password" step (`/login?step=set-password`). "Forgot password?" emails a reset link that opens `/login?step=reset`, where a new password is set without the old one. Account asks for the current password only when changing an existing one. Chat has no separate username: signed-in conversations are saved to the account, signed-out chats stay in the browser on the per-network trial, and on sign-in chat moves any chats saved in that browser (including old username threads) into the account. The first signed-in chat creates the account's free key on the server if it has none. Five failures lock the email for 15 minutes. Magic links last `MAGIC_LINK_TTL_SECONDS` (default 900), are single use, and are limited per IP and per email. Sessions last `SESSION_TTL_SECONDS` (default 14 days). Key rotation bumps the session generation, so old cookies stop working. The cookie is `Secure`, so an `http://` local preview will not keep a session; use the HTTPS Pages URL.

API host, from the repo root, after the exports in HOSTING.md:

```bash
docker compose build
docker compose up -d
curl -sf http://127.0.0.1:8000/healthz
```

No host ports are published. `API_KEYS_PATH`, `RESILEOS_API_KEYS`, and `RESILEOS_API_KEY` still authenticate. Until the KV token is set, a key that exists only in Pages KV returns 403.

The local `api/server.py` path remains available for development.

## 6. Go-live checklist

- [ ] Stripe **live** mode products + prices + webhook
- [ ] Live `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` in the secret store (not in git)
- [ ] `RESILEOS_API_BASE_URL` points at production `/api/v1`
- [ ] `API_KEYS_PATH` shared with the Resileos host (file and env keys still work)
- [ ] `SESSION_SECRET`, `KEY_SEAL_SECRET`, `RESILEOS_PROXY_SECRET`, `EMAIL_FROM`, and either the `EMAIL` binding or `RESEND_API_KEY`
- [ ] API host `CLOUDFLARE_API_TOKEN` (Workers KV Storage Read), `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_KV_NAMESPACE_ID`
- [ ] Free-key rate limit sane; consider CAPTCHA later if abused
- [ ] Replace `mailto:hello@resileos.dev` with a real inbox
- [ ] Confirm world/guild still marked “not sold” until mounted
- [ ] Fill benchmark tables from real runs before removing “RESULTS PENDING”
- [ ] Test: free key → learn → query; Builder Checkout → claim key; cancel sub → downgrade

## 7. What is not claimed yet

- Shared demo namespace — **coming soon** (not in API)
- Guild / world routes — in source, **not mounted** on hosted API
- Benchmark numbers — scripts exist; published tables still pending
