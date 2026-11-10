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
- Functions: `functions/api/config.js`, `free-key.js`, `create-checkout-session.js`, `claim/[session_id].js`
- KV namespace `resileos-keys` bound as `KEYS` (hashed keys, email cap, IP rate limit, one-time claim)
- Plaintext env: `STRIPE_PRICE_*`, `STRIPE_SUCCESS_URL`, `STRIPE_CANCEL_URL`, `RESILEOS_SITE_URL`, `RESILEOS_API_BASE_URL`, `FREE_KEY_RATE_PER_HOUR`
- Encrypted secret: `STRIPE_SECRET_KEY` (Stripe **test** mode)
- Success URL: `https://resileosai.fun/?checkout=success`
- Cancel URL: `https://resileosai.fun/#pricing`
- Claim does not require a webhook: it retrieves the Checkout Session from Stripe, mints once, and stores the hash in KV
- Redeploy from the project root: `wrangler pages deploy public --project-name resileos`

The local `api/server.py` path remains available for development.

## 6. Go-live checklist

- [ ] Stripe **live** mode products + prices + webhook
- [ ] Live `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` in the secret store (not in git)
- [ ] `RESILEOS_API_BASE_URL` points at production `/api/v1`
- [ ] `API_KEYS_PATH` shared with the Resileos host
- [ ] Free-key rate limit sane; consider CAPTCHA later if abused
- [ ] Replace `mailto:hello@resileos.dev` with a real inbox
- [ ] Confirm world/guild still marked “not sold” until mounted
- [ ] Fill benchmark tables from real runs before removing “RESULTS PENDING”
- [ ] Test: free key → learn → query; Builder Checkout → claim key; cancel sub → downgrade

## 7. What is not claimed yet

- Shared demo namespace — **coming soon** (not in API)
- Guild / world routes — in source, **not mounted** on hosted API
- Benchmark numbers — scripts exist; published tables still pending
