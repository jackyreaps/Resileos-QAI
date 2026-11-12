"""Billing + free-key API for the Resileos landing site.

Endpoints (public, CORS open to RESILEOS_LANDING_ORIGIN):
  GET  /healthz
  POST /api/free-key                 issue a free-tier key (no card)
  POST /api/create-checkout-session  Stripe Checkout for Builder / Team
  POST /api/stripe/webhook           Stripe webhooks
  GET  /api/config                   public price/link config (no secrets)

Key records are written in the same hashed format as Resileos-QAI
configs/api_keys.json so the API host can point API_KEYS_PATH at the
same file (or sync it).
"""
from __future__ import annotations

import os
import time
from collections import defaultdict
from pathlib import Path

import stripe
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from keys import (
    count_keys_for_email,
    downgrade_customer_to_free,
    mint_key,
    upgrade_by_customer,
)

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"

app = FastAPI(title="Resileos Landing API", version="1.0.0")

_origin = os.getenv("RESILEOS_LANDING_ORIGIN", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _origin == "*" else [_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

# In-memory IP rate limit for free keys (process-local).
_free_hits: dict[str, list[float]] = defaultdict(list)
_FREE_RATE = int(os.getenv("FREE_KEY_RATE_PER_HOUR", "5"))


def _check_email(v: str | None) -> str | None:
    if v is None or v == "":
        return None
    v = v.strip()
    if "@" not in v or "." not in v.split("@")[-1]:
        raise ValueError("invalid email")
    return v


class FreeKeyRequest(BaseModel):
    email: str | None = None
    name: str = Field(default="free", max_length=64)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        return _check_email(v)


class CheckoutRequest(BaseModel):
    plan: str  # builder | founding_builder | team
    email: str | None = None

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        return _check_email(v)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


def _rate_ok(ip: str) -> bool:
    now = time.monotonic()
    window = _free_hits[ip]
    cutoff = now - 3600.0
    while window and window[0] < cutoff:
        window.pop(0)
    if len(window) >= _FREE_RATE:
        return False
    window.append(now)
    return True


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/api/config")
def public_config() -> dict:
    """Non-secret config the landing page can fetch at runtime."""
    return {
        "api_base_url": os.getenv(
            "RESILEOS_API_BASE_URL", "https://api.yourdomain.dev/api/v1"
        ),
        "checkout_enabled": bool(os.getenv("STRIPE_SECRET_KEY")),
        "plans": {
            "free": {"price_display": "$0", "quota": 5000},
            "builder": {
                "price_display": "$29/mo",
                "quota": 100_000,
                "payment_link": os.getenv("STRIPE_PAYMENT_LINK_BUILDER") or None,
            },
            "founding_builder": {
                "price_display": "$19/mo (12 months, cap 50)",
                "quota": 100_000,
            },
            "team": {
                "price_display": "$99/mo",
                "quota": 500_000,
                "payment_link": os.getenv("STRIPE_PAYMENT_LINK_TEAM") or None,
            },
            "org": {"price_display": "Custom", "quota": 0},
        },
        "demo_namespace": {
            "status": "coming_soon",
            "note": (
                "A shared pre-seeded demo namespace is planned. "
                "It is not mounted on the API today."
            ),
        },
        "mouth_default": "off",
    }


@app.post("/api/free-key")
def issue_free_key(body: FreeKeyRequest, request: Request) -> dict:
    ip = _client_ip(request)
    if not _rate_ok(ip):
        raise HTTPException(
            429,
            detail="Too many free keys from this network. Try again later.",
        )
    if body.email and count_keys_for_email(str(body.email)) >= 2:
        raise HTTPException(
            429,
            detail="This email already has free keys. Upgrade or contact support.",
        )
    plaintext, record = mint_key(
        plan="free",
        name=(body.name or "free")[:64],
        email=str(body.email) if body.email else None,
    )
    base = os.getenv(
        "RESILEOS_API_BASE_URL", "https://api.yourdomain.dev/api/v1"
    )
    return {
        "api_key": plaintext,
        "tier": record["tier"],
        "quota": record["quota"],
        "plan": record["plan"],
        "base_url": base,
        "header": "X-API-Key",
        "note": (
            "Store this key now — it is shown once. "
            "Send it as the X-API-Key header on every request. "
            "Optional mouth (LLM render) is off by default."
        ),
        "demo_namespace": "coming_soon",
        "quickstart": {
            "learn": f"curl -sS -X POST {base}/learn -H 'Content-Type: application/json' -H 'X-API-Key: {plaintext}' -d '{{\"subject\":\"alice\",\"relation\":\"parent_of\",\"obj\":\"bob\"}}'",
            "query": f"curl -sS -X POST {base}/query -H 'Content-Type: application/json' -H 'X-API-Key: {plaintext}' -d '{{\"subject\":\"alice\",\"relation\":\"parent_of\"}}'",
            "chain": f"curl -sS -X POST {base}/chain -H 'Content-Type: application/json' -H 'X-API-Key: {plaintext}' -d '{{\"start\":\"alice\",\"relations\":[\"parent_of\",\"parent_of\"]}}'",
        },
    }


@app.post("/api/create-checkout-session")
def create_checkout(body: CheckoutRequest) -> dict:
    if not stripe.api_key:
        raise HTTPException(
            503,
            detail=(
                "Stripe is not configured. Set STRIPE_SECRET_KEY, "
                "or use a Payment Link from /api/config."
            ),
        )
    price_env = {
        "builder": "STRIPE_PRICE_BUILDER",
        "founding_builder": "STRIPE_PRICE_FOUNDING_BUILDER",
        "team": "STRIPE_PRICE_TEAM",
    }.get(body.plan)
    if not price_env:
        raise HTTPException(400, detail="plan must be builder, founding_builder, or team")
    price_id = os.getenv(price_env, "")
    if not price_id:
        raise HTTPException(
            503,
            detail=f"Missing {price_env}. Create the Stripe Price and set the env var.",
        )
    success = os.getenv("STRIPE_SUCCESS_URL", "").strip()
    site = os.getenv("RESILEOS_SITE_URL", "http://127.0.0.1:8787").rstrip("/")
    if not success:
        success = site + "/chat?checkout=success"
    elif "resileosai.fun" in success and "/chat" not in success.split("?", 1)[0]:
        origin = site if "resileosai.fun" in site else "https://resileosai.fun"
        success = origin.rstrip("/") + "/chat?checkout=success"
    joiner = "&" if "?" in success else "?"
    cancel = os.getenv(
        "STRIPE_CANCEL_URL",
        os.getenv("RESILEOS_SITE_URL", "http://127.0.0.1:8787") + "/#pricing",
    )
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success + joiner + "session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel,
            customer_email=str(body.email) if body.email else None,
            metadata={"plan": body.plan},
            allow_promotion_codes=True,
        )
    except Exception as e:
        raise HTTPException(502, detail=f"Stripe error: {e}") from e
    return {"id": session.id, "url": session.url}


@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request) -> dict:
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(503, detail="STRIPE_WEBHOOK_SECRET not set")
    try:
        event = stripe.Webhook.construct_event(payload, sig, secret)
    except Exception as e:
        raise HTTPException(400, detail=f"Webhook signature error: {e}") from e

    etype = event["type"]
    data = event["data"]["object"]

    if etype == "checkout.session.completed":
        plan = (data.get("metadata") or {}).get("plan") or "builder"
        email = data.get("customer_details", {}).get("email") or data.get(
            "customer_email"
        )
        customer_id = data.get("customer")
        # Prefer upgrading an existing free key tied later; for now mint paid key.
        # Operator emails the key from Stripe dashboard metadata or a follow-up mailer.
        plaintext, record = mint_key(
            plan=plan if plan in ("builder", "founding_builder", "team", "org") else "builder",
            name=f"stripe:{plan}",
            email=email,
            stripe_customer_id=customer_id,
        )
        # Stash plaintext only in server logs is unsafe; return nothing.
        # Persist a one-time claim file the success page can redeem by session id.
        claim_dir = Path(os.getenv("CLAIM_DIR", str(ROOT / "data" / "claims")))
        claim_dir.mkdir(parents=True, exist_ok=True)
        sid = data.get("id")
        if sid:
            (claim_dir / f"{sid}.json").write_text(
                __import__("json").dumps(
                    {
                        "api_key": plaintext,
                        "tier": record["tier"],
                        "quota": record["quota"],
                        "plan": record["plan"],
                        "base_url": os.getenv(
                            "RESILEOS_API_BASE_URL",
                            "https://api.yourdomain.dev/api/v1",
                        ),
                        "header": "X-API-Key",
                    }
                ),
                encoding="utf-8",
            )

    elif etype == "customer.subscription.deleted":
        customer_id = data.get("customer")
        if customer_id:
            downgrade_customer_to_free(customer_id)

    elif etype in ("customer.subscription.updated",):
        # Optional: map price id → plan on upgrades. Left as operator hook.
        pass

    return {"received": True}


@app.get("/api/claim/{session_id}")
def claim_checkout_key(session_id: str) -> dict:
    """One-time redeem of the key issued by checkout.session.completed."""
    claim_dir = Path(os.getenv("CLAIM_DIR", str(ROOT / "data" / "claims")))
    path = claim_dir / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(
            404,
            detail=(
                "Key not ready yet (webhook pending) or already claimed. "
                "Refresh in a few seconds, or check your email once mailer is wired."
            ),
        )
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    path.unlink(missing_ok=True)
    return payload


# Serve the static site from the same process in local/dev deploys.
if PUBLIC.exists():
    index = PUBLIC / "index.html"
    assets_dir = PUBLIC / "assets"

    @app.get("/")
    def index_page():
        return FileResponse(index)

    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
