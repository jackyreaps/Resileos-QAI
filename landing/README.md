# Resileos landing

Exact-memory product site. Theme: **Own the record. Control the story.**

Studio loop, hubs (`user:` / `world:` / `org:`), float32 default, a free key,
and Stripe Checkout for Builder and Team. Product behavior, benches, and the
god hierarchy are in the repo root [README.md](../README.md).

## Public site

The site will be live at [https://resileosai.fun](https://resileosai.fun)
on Cloudflare Pages, in Stripe **test** mode. Pages serves the static tree
under `public/`. The billing process in `api/` is separate and reads secrets
from the host environment, not from the Pages build.

```
public/                 static site (index, self-hosted fonts, portraits)
public/assets/gods/     AI-styled god portraits; see CREDITS.md
api/                    free-key mint and Stripe Checkout / webhook
scripts/stripe_setup.py idempotent Stripe product and price creator
artifacts/              measured bench reports
CAPABILITIES.md         capability notes
DEPLOY.md               go-live notes
```

The old single `index.html` at the landing root is gone. The page lives at
`public/index.html`. Locally, one process serves that directory and the API.

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
export STRIPE_SUCCESS_URL=http://127.0.0.1:8787/?checkout=success
export STRIPE_CANCEL_URL=http://127.0.0.1:8787/#pricing
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

`.env` and `.env.live` are gitignored. Keep live-mode values in `.env.live`
or the host secret store, never in the repo.
