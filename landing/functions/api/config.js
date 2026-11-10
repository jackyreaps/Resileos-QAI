import { json, apiBase } from "../_lib.js";

export async function onRequestGet({ env }) {
  return json({
    api_base_url: apiBase(env),
    checkout_enabled: Boolean(env.STRIPE_SECRET_KEY),
    plans: {
      free: { price_display: "$0", quota: 5000 },
      builder: {
        price_display: "$29/mo",
        quota: 100000,
        payment_link: env.STRIPE_PAYMENT_LINK_BUILDER || null,
      },
      founding_builder: {
        price_display: "$19/mo (12 months, cap 50)",
        quota: 100000,
      },
      team: {
        price_display: "$99/mo",
        quota: 500000,
        payment_link: env.STRIPE_PAYMENT_LINK_TEAM || null,
      },
      org: { price_display: "Custom", quota: 0 },
    },
    demo_namespace: {
      status: "coming_soon",
      note: "A shared pre-seeded demo namespace is planned. It is not mounted on the API today.",
    },
    mouth_default: "off",
  });
}
