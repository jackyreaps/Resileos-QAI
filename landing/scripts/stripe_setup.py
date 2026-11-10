#!/usr/bin/env python3
"""Idempotently create Stripe products/prices for Resileos billing (test or live).

Reads STRIPE_SECRET_KEY from the environment. Use a test-mode secret for local
runs. Creates:
  Builder           $29/mo   → STRIPE_PRICE_BUILDER
  Founding Builder  $19/mo   → STRIPE_PRICE_FOUNDING_BUILDER
  Team              $99/mo   → STRIPE_PRICE_TEAM

Prices match docs/marketing/pricing.md. Idempotent via metadata lookup
(resileos_plan = builder|founding_builder|team).

Usage:
  export STRIPE_SECRET_KEY
  python scripts/stripe_setup.py

Does not write .env — prints the lines to paste.
"""
from __future__ import annotations

import os
import sys

PLANS = [
    {
        "plan": "builder",
        "name": "Resileos Builder",
        "description": "Builder tier — 100k requests/mo, 3 API keys (pricing.md)",
        "unit_amount": 2900,
        "env": "STRIPE_PRICE_BUILDER",
        "product_meta": {"resileos_product": "builder_monthly"},
    },
    {
        "plan": "founding_builder",
        "name": "Resileos Founding Builder",
        "description": "Founding Builder — $19/mo locked 12 months, cap 50 (pricing.md §4)",
        "unit_amount": 1900,
        "env": "STRIPE_PRICE_FOUNDING_BUILDER",
        "product_meta": {"resileos_product": "founding_builder_monthly"},
    },
    {
        "plan": "team",
        "name": "Resileos Team",
        "description": "Team tier — 500k requests/mo, 10 API keys (pricing.md)",
        "unit_amount": 9900,
        "env": "STRIPE_PRICE_TEAM",
        "product_meta": {"resileos_product": "team_monthly"},
    },
]


def main() -> int:
    key = os.getenv("STRIPE_SECRET_KEY", "").strip()
    if not key:
        print("Set STRIPE_SECRET_KEY to your Stripe secret key.", file=sys.stderr)
        return 1
    try:
        import stripe
    except ImportError:
        print("pip install stripe", file=sys.stderr)
        return 1

    stripe.api_key = key
    # Test-mode secret keys carry a "test" marker in the prefix. Live keys do not.
    mode = "TEST" if "test" in key[:12] else "LIVE"
    print(f"# Stripe mode: {mode}")
    print("# Paste into .env:\n")

    # Index existing products by metadata
    existing_products: dict[str, str] = {}
    for prod in stripe.Product.list(limit=100).auto_paging_iter():
        meta = prod.get("metadata") or {}
        plan = meta.get("resileos_plan") or meta.get("resileos_product", "").replace(
            "_monthly", ""
        )
        if plan:
            existing_products[plan] = prod["id"]

    existing_prices: dict[str, str] = {}
    for price in stripe.Price.list(limit=100, active=True).auto_paging_iter():
        meta = price.get("metadata") or {}
        plan = meta.get("resileos_plan")
        if plan and price.get("recurring", {}).get("interval") == "month":
            existing_prices[plan] = price["id"]

    lines = []
    for spec in PLANS:
        plan = spec["plan"]
        if plan in existing_prices:
            price_id = existing_prices[plan]
            print(f"# reused price for {plan}: {price_id}")
        else:
            product_id = existing_products.get(plan)
            if not product_id:
                product = stripe.Product.create(tax_code="txcd_10103001", 
                    name=spec["name"],
                    description=spec["description"],
                    metadata={
                        "resileos_plan": plan,
                        **spec["product_meta"],
                    },
                )
                product_id = product["id"]
                print(f"# created product {plan}: {product_id}")
            else:
                print(f"# reused product {plan}: {product_id}")
            price = stripe.Price.create(
                product=product_id,
                unit_amount=spec["unit_amount"],
                currency="usd",
                recurring={"interval": "month"},
                metadata={"resileos_plan": plan},
            )
            price_id = price["id"]
            print(f"# created price {plan}: {price_id}")
        lines.append(f"{spec['env']}={price_id}")

    print()
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
