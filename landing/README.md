# Resileos landing

Theme: **Own the record. Control the story.**

Exact-memory product site. Titanos (`ask` / `ask_list` / `chain`), the god
hierarchy, the Studio loop, hubs (`user:` / `world:` / `org:`), float32
default, a free key, and Stripe Checkout for Builder and Team. Self-hosted
OFL fonts: Instrument Serif, Inter, and JetBrains Mono. Portraits are in
`public/assets/gods/` (`CREDITS.md`). Lenis is vendored at
`public/assets/vendor/`. Product behavior and benches are in the repo root
[README.md](../README.md).

```
public/                     static site (Cloudflare Pages output)
public/index.html           home
public/how-it-works.html    engine, proof, dated facts  → /how-it-works
public/kin.html             patrons, Kin, Demi-gods     → /kin
public/pricing.html         plans and the free-key form → /pricing
public/credits.html         portrait credits            → /credits
public/chat.html            product chat                → /chat
public/assets/gods/         expanded portraits (bronze, marble, crystal)
public/assets/motion/       short decorative light sweeps
public/assets/fonts/        Instrument Serif, Inter, JetBrains Mono
public/assets/vendor/       vendored Lenis
functions/api/              Cloudflare Pages Functions (sign-in, account, free key, checkout, claim)
api/                        local FastAPI server for the same billing routes
scripts/stripe_setup.py     idempotent Stripe product and price creator
wrangler.toml               Pages project and the KEYS KV binding
artifacts/                  measured bench reports
CAPABILITIES.md             capability notes
DEPLOY.md                   go-live notes
```

Pretty URLs are Cloudflare Pages defaults (`how-it-works.html` is served at
`/how-it-works`). Do not add a `_redirects` rule from `/chat` to
`/chat.html`. That rewrite looped with the Pages redirect. Old homepage
hashes such as `/#pricing` are forwarded in the browser to the new page.

## Public site

The site is live at [https://resileosai.fun](https://resileosai.fun) and
[https://www.resileosai.fun](https://www.resileosai.fun) on Cloudflare Pages
(also [https://resileos.pages.dev](https://resileos.pages.dev)), in Stripe
**test** mode. Pages serves `public/`. Billing routes are Pages Functions in
`functions/api/`, with the KV binding `KEYS` from `wrangler.toml`.
`STRIPE_SECRET_KEY` is an encrypted Pages secret, not a file in this tree.
Checkout success and cancel URLs point at https://resileosai.fun.

## Run locally in test mode

Use Stripe **test** mode. Secrets stay in the shell or in a gitignored file
(`.env` or `.env.live`). This README names the variables only. Copy
`.env.example`, fill the values outside git, and do not commit them.

```bash
cd landing
python3 -m venv .venv
source .venv/bin/activate
pip install -r api/requirements.txt
mkdir -p data
cp .env.example .env
```

Export these before starting the server:

- `API_KEYS_PATH` — hashed key file (local default `./data/api_keys.json`)
- `RESILEOS_API_BASE_URL` — Resileos `/api/v1` base shown to users
- `RESILEOS_SITE_URL` — this site, `http://127.0.0.1:8787` locally
- `RESILEOS_LANDING_ORIGIN` — CORS origin; optional, default allows any origin
- `FREE_KEY_RATE_PER_HOUR` — optional, default 5
- `STRIPE_SECRET_KEY` — test-mode secret from the Stripe dashboard
- `STRIPE_WEBHOOK_SECRET` — signing secret for the local webhook forwarder
- `STRIPE_PRICE_BUILDER`
- `STRIPE_PRICE_FOUNDING_BUILDER`
- `STRIPE_PRICE_TEAM`
- `STRIPE_SUCCESS_URL` — optional, defaults from `RESILEOS_SITE_URL`
- `STRIPE_CANCEL_URL` — optional, defaults from `RESILEOS_SITE_URL`
- `STRIPE_PAYMENT_LINK_BUILDER` — optional Payment Link fallback
- `STRIPE_PAYMENT_LINK_TEAM` — optional Payment Link fallback

`scripts/stripe_setup.py` reads `STRIPE_SECRET_KEY` and prints
`STRIPE_PRICE_BUILDER`, `STRIPE_PRICE_FOUNDING_BUILDER`, and
`STRIPE_PRICE_TEAM`. It does not write an env file. Run it only with a
test-mode key when you are working locally.

```bash
export API_KEYS_PATH=./data/api_keys.json
export RESILEOS_API_BASE_URL=http://127.0.0.1:8000/api/v1
export RESILEOS_SITE_URL=http://127.0.0.1:8787
export STRIPE_SUCCESS_URL=http://127.0.0.1:8787/chat?checkout=success
export STRIPE_CANCEL_URL=http://127.0.0.1:8787/pricing
# also export STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, and STRIPE_PRICE_*
uvicorn api.server:app --app-dir . --host 127.0.0.1 --port 8787 --reload
```

Open http://127.0.0.1:8787

- Free key: the form calls `POST /api/free-key` and shows the key once.
- Checkout: without `STRIPE_SECRET_KEY` and the price variables, the buttons
  return a clear configuration error. Payment Links work when those optional
  variables are set.
- Webhooks: forward Stripe test events to
  `http://127.0.0.1:8787/api/stripe/webhook` and put that forwarder’s signing
  secret in `STRIPE_WEBHOOK_SECRET`.

The live Pages claim route does not need that webhook. It reads the Checkout
Session and stores the key hash in KV. `.env` and `.env.live` are gitignored.
Keep live-mode values in `.env.live` or the host secret store, never in the repo.
